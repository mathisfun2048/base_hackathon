"""O5 -- Degradation vulnerability + detection (defensive) (SPEC S2, S4, S7).

Using a public DoD/throughput/C-rate/temperature aging model, quantify how much
a compromised controller could ACCELERATE fleet aging within a detectability
budget eps, the telemetry SIGNATURE that reveals it, and the firmware/operational
BOUNDS that cap it. NO destruction-optimal schedule is produced (SPEC S7): we
sweep a generic eps-bounded wear deviation and report the sensitivity, signature,
and mitigation.

  benign        : price-optimal daily cycle (charge cheap, discharge dear)
  within-eps    : benign + eps-scaled extra cycling and a wrong-way bias
                  (charging into scarcity), the shape that maximizes wear per
                  unit of exposed anomaly.

DEFENSE paired with the result: firmware/operational caps -- C-rate ceiling,
DoD floor, equivalent-full-cycle/day budget, min dwell, ramp limit -- plus the
telemetry signature (EFC/day, directional bias, cross-unit correlation, DoD-floor
breaches) that an operator monitors.
"""
from __future__ import annotations

import numpy as np

from data.fetch_ercot import find_stressed_interval
from models import degradation, detection
from sims._common import savefig, write_table, annotate_defense, C_HARM, C_MAIN, C_SAFE, C_WARN, plt

UNIT_KW = degradation.UNIT_KW


def _benign_soc(price, T):
    """Price-optimal SoC path: one clean daily cycle, charge cheap / discharge
    dear, staying within [0.18, 0.82] so the wear model is not rail-saturated."""
    t = np.linspace(0, 1, T, endpoint=False)
    # phase so SoC peaks before the evening price peak (discharge into it)
    return 0.5 + 0.32 * np.sin(2 * np.pi * (t - 0.15))


def _price_optimal_sign(price):
    p = np.asarray(price, dtype=float)
    s = np.sign(p - p.mean())
    s[s == 0] = 1.0
    return s


def run(det_target: float = 0.9):
    stressed, _ = find_stressed_interval()
    synthetic = not stressed.real
    price = stressed.price_series
    T = len(price)
    benign_soc = _benign_soc(price, T)
    posign = _price_optimal_sign(price)
    high_price = (posign > 0).astype(float)              # 1 when discharging is optimal

    # Within-eps wear: dominant mean-zero high-frequency micro-cycling in SoC
    # (strictly adds equivalent-full-cycles => monotone aging) plus a small
    # wrong-way tilt (SoC rising into scarcity = charging into high prices),
    # which the directional-bias detector keys on.
    hf = np.sin(np.linspace(0, 16 * np.pi, T))
    wrongway_soc = high_price - high_price.mean()        # +ve during scarcity
    wear_dir = 0.85 * hf + 0.15 * wrongway_soc / (np.max(np.abs(wrongway_soc)) + 1e-9)

    eps_grid = np.linspace(0.0, 1.0, 21)                 # per-unit deviation frac
    ar_b = degradation.aging_from_soc(benign_soc)

    damage_ratio, efc_ratio, bias, dod_breach, efc_day = [], [], [], [], []
    for eps in eps_grid:
        soc = np.clip(benign_soc + eps * 0.12 * wear_dir, 0.05, 0.95)
        ar = degradation.aging_from_soc(soc)
        damage_ratio.append(ar["damage_eff"] / (ar_b["damage_eff"] + 1e-15))
        efc_ratio.append(ar["efc"] / (ar_b["efc"] + 1e-15))
        efc_day.append(ar["efc_per_day"])
        # directional bias: SoC rising (charging) during high-price intervals
        dsoc = np.diff(soc, prepend=soc[0])
        denom = np.sum(np.abs(dsoc)) + 1e-9
        bias.append(float(np.sum(dsoc * (posign > 0)) / denom))
        dod_breach.append(float(np.mean(soc < 0.10)))
    damage_ratio = np.array(damage_ratio)
    efc_ratio = np.array(efc_ratio)
    bias = np.array(bias)

    # detection probability (fleet correlation+bias) vs eps
    roc = detection.roc_vs_eps(eps_grid, n_units=20, T=8, n_trials=80, far=0.05)
    p_det = roc["detection_prob"]
    above = np.where(p_det >= det_target)[0]
    eps_star = float(eps_grid[above[0]]) if len(above) else float(eps_grid[-1])
    damage_at_star = float(np.interp(eps_star, eps_grid, damage_ratio))

    bounds = degradation.protective_bounds()

    # ---- figure ----
    fig, (axA, axB) = plt.subplots(1, 2, figsize=(11.5, 4.4))
    axA.plot(eps_grid, damage_ratio, color=C_HARM, lw=2.2, label="aging-rate multiplier (vs benign)")
    axA.plot(eps_grid, efc_ratio, color=C_WARN, lw=1.8, ls="--", label="equiv-full-cycles multiplier")
    axA.axhline(1.0, color=C_MAIN, ls=":", lw=1.2)
    axA.set_xlabel("stealth budget  $\\varepsilon$  (per-unit deviation fraction)")
    axA.set_ylabel("fleet aging acceleration (x benign)")
    axA.set_title("O5  Within-$\\varepsilon$ aging acceleration")
    axA.legend(loc="upper left", fontsize=8.5)

    bias_dev = bias - bias[0]     # increase in wrong-way alignment vs benign
    axB.plot(eps_grid, bias_dev, color=C_HARM, lw=2.0,
             label="directional-bias shift (toward wrong-way)")
    axB.plot(eps_grid, p_det, color=C_MAIN, lw=2.0, ls="--", label="fleet detection prob (5% FAR)")
    axB.axvline(eps_star, color=C_SAFE, ls="-.", lw=1.4)
    axB.set_xlabel("stealth budget  $\\varepsilon$")
    axB.set_ylabel("detection statistic / probability")
    axB.set_title("O5  Telemetry signature separates it")
    axB.annotate(f"set-point $\\varepsilon^*$={eps_star:.2f}\naging capped at "
                 f"{damage_at_star:.2f}x",
                 xy=(eps_star, det_target), xytext=(eps_star - 0.02, 0.45),
                 ha="right", color=C_SAFE, fontsize=9,
                 arrowprops=dict(arrowstyle="->", color=C_SAFE))
    axB.legend(loc="upper left", fontsize=8.5)
    annotate_defense(axB, "caps: C-rate<=0.5, DoD floor 10%, <=2 EFC/day,\n"
                          "dwell>=5min; monitor EFC/day + bias + correlation")
    fig_path = savefig(fig, "O5_degradation.png")

    # ---- table ----
    rows = [
        ["data source (price shape)", stressed.source[:60]],
        ["benign damage/day (frac life)", f"{ar_b['damage_per_day']:.3e}"],
        ["benign EFC/day", f"{ar_b['efc_per_day']:.2f}"],
        ["max aging multiplier at eps=1", f"{damage_ratio[-1]:.2f}x"],
        ["aging multiplier at set-point eps*", f"{damage_at_star:.2f}x"],
        ["detection set-point eps*", f"{eps_star:.2f}"],
        ["-- protective bounds (mitigation) --", ""],
        ["max C-rate", f"{bounds['max_c_rate']}"],
        ["DoD floor", f"{bounds['dod_floor']}"],
        ["max EFC/day", f"{bounds['max_efc_per_day']}"],
        ["min dwell (s)", f"{bounds['min_dwell_s']}"],
        ["max ramp (kW/s)", f"{bounds['max_ramp_kw_s']:.3f}"],
        ["-- monitored signature --", ""],
        ["max cross-unit correlation", f"{detection.monitoring_thresholds()['max_cross_unit_correlation']}"],
        ["max directional bias", f"{detection.monitoring_thresholds()['max_directional_bias']}"],
    ]
    tab_path = write_table("O5_degradation.csv", ["quantity", "value"], rows)

    para = (
        f"O5: A compromised controller operating within the stealth budget can "
        f"accelerate fleet aging up to ~{damage_ratio[-1]:.1f}x benign at eps=1, but the "
        f"telemetry signature -- elevated equivalent-full-cycles/day, a persistent "
        f"wrong-way directional bias, DoD-floor breaches, and cross-unit correlation -- "
        f"makes detection near-certain by eps*={eps_star:.2f}, capping stealthy "
        f"acceleration at ~{damage_at_star:.2f}x. Firmware/operational bounds "
        f"(C-rate<=0.5, 10% DoD floor, <=2 EFC/day, >=5 min dwell, ramp limit) cap the "
        f"residual. No destruction-optimal schedule is produced."
        + (" [price shape: ERCOT offer-cap scarcity reference]" if synthetic else " [prices: real ERCOT]")
    )
    return {"eps_star": eps_star, "damage_max": float(damage_ratio[-1]),
            "damage_at_star": damage_at_star, "bounds": bounds, "synthetic": synthetic,
            "fig": fig_path, "table": tab_path, "paragraph": para}


if __name__ == "__main__":
    out = run()
    print(out["paragraph"])
    print("figure:", out["fig"])
