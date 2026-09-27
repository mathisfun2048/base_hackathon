"""O4 -- Stealth frontier: max harm subject to a detectability budget eps (SPEC S2).

Trace harm(eps): the most cost inflation an eps-bounded, per-unit-synchronized
deviation can produce, alongside the probability that the O6 detector catches it.
eps is a GENERIC per-interval/per-unit anomaly bound (SPEC S0), NOT tuned to any
real detector. The mitigation SET-POINT is the eps at which detection becomes
near-certain: cap the allowed per-unit telemetry deviation there and harm is
bounded to harm(eps*).

Consistent eps: a per-unit deviation fraction in [0,1]. It drives
  * harm  = cost inflation from an aggregate deviation eps * FLEET_MW at a
            stressed price anchor (models.adversary.max_cost_harm_within_eps)
  * P_det = detection probability of the correlation+bias statistic at 5% FAR
            (models.detection.roc_vs_eps)
"""
from __future__ import annotations

import numpy as np

from data.fetch_ercot import find_stressed_interval
from models.price import calibrate_to_observed, load_for_price
from models import adversary, detection
from sims._common import savefig, write_table, annotate_defense, C_HARM, C_MAIN, C_SAFE, plt

FLEET_MW = 400.0


def run(det_target: float = 0.9):
    stressed, _ = find_stressed_interval()
    synthetic = not stressed.real
    L_obs = load_for_price(stressed.peak_price)
    cal = calibrate_to_observed(stressed.peak_price, L_obs)

    eps_grid = np.linspace(0.0, 1.0, 21)     # per-unit deviation fraction
    # aggregate MW deviation if every unit deviates by eps in the same direction
    T = 8                                     # a 2-hour stressed window (8x15min)
    L = np.full(T, L_obs)
    Qb = np.zeros(T)

    harm = np.array([
        adversary.max_cost_harm_within_eps(L, cal["price"], Qb, eps * FLEET_MW)["harm"]
        for eps in eps_grid])

    roc = detection.roc_vs_eps(eps_grid, n_units=20, T=8, n_trials=80, far=0.05)
    p_det = roc["detection_prob"]

    # mitigation set-point: smallest eps with detection >= target
    above = np.where(p_det >= det_target)[0]
    eps_star = float(eps_grid[above[0]]) if len(above) else float(eps_grid[-1])
    harm_star = float(np.interp(eps_star, eps_grid, harm))

    # ---- figure: harm(eps) with detection overlay ----
    fig, ax = plt.subplots()
    ax.plot(eps_grid, harm / 1e6, color=C_HARM, lw=2.2, label="max cost inflation harm($\\varepsilon$)")
    ax.set_xlabel("stealth budget  $\\varepsilon$  (per-unit deviation fraction)")
    ax.set_ylabel("system cost inflation over 2 h ($M)", color=C_HARM)
    ax.tick_params(axis="y", labelcolor=C_HARM)
    ax.set_title("O4  Stealth frontier: harm vs detectability\n"
                 "(stressed anchor; " + ("offer-cap scarcity reference)" if synthetic else "real ERCOT prices)"))

    ax2 = ax.twinx()
    ax2.plot(eps_grid, p_det, color=C_MAIN, lw=2.0, ls="--", label="detection probability (5% FAR)")
    ax2.set_ylabel("detection probability", color=C_MAIN)
    ax2.tick_params(axis="y", labelcolor=C_MAIN)
    ax2.set_ylim(-0.03, 1.05)
    ax2.grid(False)

    ax.axvline(eps_star, color=C_SAFE, ls="-.", lw=1.5)
    ax.annotate(f"mitigation set-point\n$\\varepsilon^*$={eps_star:.2f}  "
                f"(P$_{{det}}\\geq${det_target:.0%})",
                xy=(eps_star, harm_star / 1e6),
                xytext=(eps_star - 0.02, (harm.max() / 1e6) * 0.55),
                ha="right", color=C_SAFE, fontsize=9,
                arrowprops=dict(arrowstyle="->", color=C_SAFE))
    l1, lab1 = ax.get_legend_handles_labels()
    l2, lab2 = ax2.get_legend_handles_labels()
    ax.legend(l1 + l2, lab1 + lab2, loc="upper left", fontsize=8.5)
    annotate_defense(ax, f"alarm on per-unit deviation > {eps_star:.2f}; harm capped\n"
                          f"at ~${harm_star/1e6:.1f}M before detection is near-certain")
    fig_path = savefig(fig, "O4_stealth_frontier.png")

    # ---- table ----
    rows = []
    for e, h, pd in zip(eps_grid, harm, p_det):
        rows.append([f"{e:.2f}", f"{h:,.0f}", f"{pd:.2f}"])
    tab_path = write_table("O4_stealth_frontier.csv",
                           ["eps", "cost_inflation_2h_usd", "detection_prob"], rows)

    para = (
        f"O4: Harm rises monotonically with the stealth budget eps, but so does the "
        f"probability the correlation+bias detector fires. Detection becomes "
        f"near-certain (>={det_target:.0%}) at eps*={eps_star:.2f} per-unit deviation, "
        f"which caps stealthy cost inflation at ~${harm_star/1e6:.1f}M over a 2-hour "
        f"stressed window. The mitigation set-point is therefore a per-unit "
        f"telemetry-deviation alarm at eps*={eps_star:.2f}"
        + (" [scarcity anchor: ERCOT offer-cap reference]." if synthetic else " [prices: real ERCOT].")
    )
    return {"eps_star": eps_star, "harm_star": harm_star, "eps_grid": eps_grid,
            "harm": harm, "p_det": p_det, "synthetic": synthetic,
            "fig": fig_path, "table": tab_path, "paragraph": para}


if __name__ == "__main__":
    out = run()
    print(out["paragraph"])
    print("figure:", out["fig"])
