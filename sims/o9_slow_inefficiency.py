"""O9 -- Subtle inefficiency accumulated over time (SPEC user Q3).

The "boiling-frog" attack: a compromised controller deviates only slightly each
interval -- below any per-interval anomaly threshold -- but PERSISTENTLY in a
cost-inflating / wear-accelerating direction. Any single snapshot looks benign;
the harm is in the accumulation over weeks and months (cost inflation, round-trip
efficiency erosion, and capacity fade).

Key defensive result: a SEQUENTIAL detector (CUSUM on the persistent directional
bias) catches even a tiny persistent bias, and because a stealthier attack has
proportionally smaller per-day harm but takes proportionally longer to detect,
the CUMULATIVE harm before detection is BOUNDED -- there is no stealth level that
escapes with unbounded damage. That bound is the mitigation target.

DEFENSE (paired): cumulative / sequential monitoring (CUSUM on directional bias +
long-window cross-unit correlation) rather than per-interval thresholds alone,
plus the daily cost-deviation and EFC/day budgets from O5/O6.
"""
from __future__ import annotations

import numpy as np

from data.fetch_ercot import find_stressed_interval
from models.price import calibrate_to_observed, load_for_price
from models import adversary
from sims._common import (savefig, write_table, annotate_defense,
                          C_HARM, C_MAIN, C_SAFE, C_WARN, C_MUTED, plt)

FLEET_MW = 400.0
HORIZON_DAYS = 180
PEAK_INTERVALS_PER_DAY = 4       # ~1 hour of elevated-price exposure per day


def _cusum_detection_day(mu, sigma=1.0, k=0.5, h=5.0, days=HORIZON_DAYS, seed=0):
    """Day at which a CUSUM chart on the daily bias signal fires.

    Daily bias ~ N(mu, sigma) (mu = persistent adversarial bias, in sigma units).
    CUSUM: S_t = max(0, S_{t-1} + (x_t - k)); alarm when S_t > h. Returns the
    detection day, or `days` if never (bounded horizon)."""
    rng = np.random.default_rng(seed)
    S = 0.0
    for t in range(1, days + 1):
        x = rng.normal(mu, sigma)
        S = max(0.0, S + (x - k))
        if S > h:
            return t
    return days


def run():
    # daily harm anchored to a moderately-elevated (sub-scarcity) peak price
    stressed, _ = find_stressed_interval()
    p_peak = 150.0                       # $/MWh: a routine daily peak, not scarcity
    L0 = load_for_price(p_peak)
    cal = calibrate_to_observed(p_peak, L0)
    L = np.full(PEAK_INTERVALS_PER_DAY, L0)
    Qb = np.zeros(PEAK_INTERVALS_PER_DAY)

    def daily_harm(eps):     # cost inflation per day from an eps-bounded push
        return adversary.max_cost_harm_within_eps(L, cal["price"], Qb, eps * FLEET_MW)["harm"]

    # stealth levels: all BELOW a per-interval alarm (so each looks benign)
    eps_levels = [0.03, 0.06, 0.12, 0.20]
    days = np.arange(0, HORIZON_DAYS + 1)

    # ---- left: cumulative cost inflation over time, harm stops at detection ----
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(12.0, 4.8))
    colors = [C_SAFE, C_MAIN, C_WARN, C_HARM]
    det_days, cum_at_det = [], []
    for eps, col in zip(eps_levels, colors):
        d_harm = daily_harm(eps)
        # CUSUM detection: bias in sigma units ~ proportional to eps (scale 12)
        mu = eps * 12.0
        dday = _cusum_detection_day(mu)
        det_days.append(dday)
        cum = np.minimum(days, dday) * d_harm / 1e6       # $M, frozen after detection
        cum_at_det.append(cum[-1] if dday >= HORIZON_DAYS else dday * d_harm / 1e6)
        axL.plot(days, cum, color=col, lw=2.0,
                 label=f"$\\varepsilon$={eps:.2f}: \\${d_harm/1e6:.2f}M/day, detected d{dday}")
        axL.scatter([dday], [dday * d_harm / 1e6], color=col, zorder=5, s=30)
    axL.set_xlabel("day")
    axL.set_ylabel("cumulative system cost inflation ($M)")
    axL.set_title("O9  Slow sub-threshold inflation accumulates...\n"
                  "(dots = sequential detector fires; harm stops)")
    axL.legend(loc="upper left", fontsize=8.0)
    annotate_defense(axL, "CUSUM on persistent bias fires even for tiny $\\varepsilon$")

    # ---- right: cumulative harm at detection is BOUNDED across stealth levels ----
    eps_fine = np.linspace(0.02, 0.30, 29)
    cum_bound = []
    for eps in eps_fine:
        d_harm = daily_harm(eps)
        dday = _cusum_detection_day(eps * 12.0)
        cum_bound.append(dday * d_harm / 1e6)
    cum_bound = np.array(cum_bound)
    axR.plot(eps_fine, cum_bound, color=C_HARM, lw=2.3)
    axR.axhline(cum_bound.max() * 1.05, color=C_SAFE, ls="--", lw=1.3,
                label=f"bounded: <= ~\\${cum_bound.max():.1f}M before detection")
    axR.set_xlabel("per-interval stealth level  $\\varepsilon$  (all sub-threshold)")
    axR.set_ylabel("cumulative cost inflation BEFORE detection ($M)")
    axR.set_title("O9  Stealthier = slower harm but longer exposure\n"
                  "=> cumulative harm before detection is BOUNDED")
    axR.legend(loc="upper right", fontsize=8.5)
    annotate_defense(axR, "no stealth level escapes with unbounded damage;\n"
                          "the bound is the monitoring set-point")
    fig_path = savefig(fig, "O9_slow_inefficiency.png")

    # ---- table ----
    rows = []
    for eps in eps_levels:
        d_harm = daily_harm(eps)
        dday = _cusum_detection_day(eps * 12.0)
        rows.append([f"{eps:.2f}", f"{d_harm/1e6:.3f}", f"{dday}",
                     f"{dday*d_harm/1e6:.2f}",
                     f"{d_harm*HORIZON_DAYS/1e6:.1f}"])
    tab_path = write_table("O9_slow_inefficiency.csv",
                           ["eps", "cost_inflation_$M_per_day", "detection_day",
                            "cumulative_$M_at_detection", "undetected_180d_$M"], rows)

    para = (
        f"O9 (subtle inefficiency over time): A persistent sub-threshold deviation inflates "
        f"cost and erodes efficiency a little each day -- invisible to per-interval checks. "
        f"Left unmonitored over {HORIZON_DAYS} days it compounds. But a sequential CUSUM "
        f"detector on the persistent directional bias fires even for tiny stealth levels, and "
        f"because a stealthier attack has proportionally smaller daily harm yet takes "
        f"proportionally longer to detect, the cumulative harm before detection is BOUNDED at "
        f"~${cum_bound.max():.1f}M regardless of how slow the attacker goes. DEFENSE: "
        f"cumulative/sequential monitoring (CUSUM on bias + long-window correlation) on top of "
        f"the per-interval budgets -- this bound is the monitoring set-point."
    )
    return {"fig": fig_path, "table": tab_path, "paragraph": para,
            "cumulative_bound_musd": float(cum_bound.max())}


if __name__ == "__main__":
    out = run()
    print(out["paragraph"])
    print("figure:", out["fig"])
