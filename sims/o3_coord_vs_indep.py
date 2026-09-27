"""O3 -- Correlation premium: harm(coordinated)/harm(independent) vs phi (SPEC S2).

Mirror of the owner-side coordination premium rho (research.tex S "coordination
value"). Below the local threshold the problem is SEPARABLE -- an adversary
gains nothing from coordination (ratio ~ 1). Only past the threshold, where the
shared feeder constraint binds, does synchronizing many units produce harm that
diversified (independent) dispatch does not (ratio > 1).

  coordinated : all phi co-located units act together   -> aggregate ~ phi*unit
  independent : units act on their own state (decorrelated) -> aggregate ~ sqrt(phi)

DEFENSE paired with the result: the premium only exists above phi*, so the
same per-feeder penetration cap (O1) plus the cross-unit correlation detector
(O6) remove it -- capping correlation collapses the premium back to ~1.
"""
from __future__ import annotations

import numpy as np

from data.topology import representative_feeder
from models import feasibility, adversary
from models.degradation import UNIT_KW
from sims._common import savefig, write_table, annotate_defense, C_HARM, C_MAIN, C_SAFE, C_MUTED, plt


def _independent_harm(fdr, node, phi, unit_mw, n_mc=200, seed=3):
    """Expected feeder-stress harm when phi units act independently.

    Each unit independently discharges/charges/idles (decorrelated), so the
    aggregate injection is a near-zero-mean sum ~ sqrt(phi)."""
    rng = np.random.default_rng(seed + phi)
    harms = np.empty(n_mc)
    for m in range(n_mc):
        signs = rng.choice([-1.0, 0.0, 1.0], size=phi, p=[0.4, 0.2, 0.4])
        agg = float(signs.sum()) * unit_mw
        harms[m] = adversary.J_stress(fdr, feasibility.inject_at(fdr, node, agg))
    return float(harms.mean())


def run(phi_max: int = 400, unit_kw: float = UNIT_KW):
    fdr = representative_feeder()
    node = fdr.coloc_node
    unit_mw = unit_kw / 1000.0

    phis = np.arange(2, phi_max + 1, 2)
    # coordinated adversary picks the worse of charge (+load) / discharge (reverse)
    harm_coord = np.array([
        max(adversary.J_stress(fdr, feasibility.inject_at(fdr, node, +phi * unit_mw)),
            adversary.J_stress(fdr, feasibility.inject_at(fdr, node, -phi * unit_mw)))
        for phi in phis])
    harm_indep = np.array([_independent_harm(fdr, node, int(phi), unit_mw) for phi in phis])

    # regularized coordination premium: exactly 1 when neither regime harms,
    # rising once coordinated dispatch crosses the feeder limit.
    floor = 1e-3
    premium = (harm_coord + floor) / (harm_indep + floor)
    premium = np.where(harm_coord <= floor, 1.0, premium)

    # threshold: first phi where coordinated dispatch violates ANY limit
    # (same definition as O1, so the two outputs agree).
    phi_star = None
    for phi in phis:
        if (feasibility.violations(fdr, feasibility.inject_at(fdr, node, +phi * unit_mw))["any"]
                or feasibility.violations(fdr, feasibility.inject_at(fdr, node, -phi * unit_mw))["any"]):
            phi_star = int(phi)
            break

    # ---- figure ----
    fig, (axA, axB) = plt.subplots(1, 2, figsize=(11.5, 4.4))
    axA.plot(phis, harm_coord, color=C_HARM, label="coordinated (synchronized)")
    axA.plot(phis, harm_indep, color=C_MAIN, label="independent (diversified)")
    axA.set_xlabel("co-located units $\\varphi$")
    axA.set_ylabel("expected feeder-stress harm (MW-equiv)")
    axA.set_title("O3  Coordinated vs independent harm")
    if phi_star:
        axA.axvline(phi_star, color=C_SAFE, ls="--", lw=1.3)
    axA.legend(loc="upper left")

    axB.plot(phis, np.clip(premium, 1.0, None), color=C_HARM, lw=2)
    axB.axhline(1.0, color=C_MAIN, ls=":", lw=1.3, label="separability (ratio = 1)")
    axB.set_yscale("log")
    axB.set_xlabel("co-located units $\\varphi$")
    axB.set_ylabel("coordination premium  harm(coord)/harm(indep)")
    axB.set_title("O3  Premium $\\approx$1 below threshold, unbounded above")
    if phi_star:
        axB.axvline(phi_star, color=C_SAFE, ls="--", lw=1.3,
                    label=f"threshold $\\varphi^*\\approx${phi_star}")
    axB.set_ylim(0.8, max(premium.max() * 2, 10))
    axB.text(0.97, 0.62, "above $\\varphi^*$: diversified dispatch\nnever binds the limit\n=> premium unbounded",
             transform=axB.transAxes, ha="right", va="top", fontsize=8, color=C_MUTED)
    axB.legend(loc="upper left")
    annotate_defense(axB, "cap correlation (O6) + per-feeder penetration (O1)\n"
                          "-> premium collapses back to ~1")
    fig_path = savefig(fig, "O3_coordination_premium.png")

    # ---- table ----
    sample = [10, 50, 100, 150, 200, 300, 400]
    rows = [["phi", "harm_coordinated", "harm_independent", "premium"]]
    for s in sample:
        k = np.argmin(np.abs(phis - s))
        rows.append([int(phis[k]), f"{harm_coord[k]:.4f}", f"{harm_indep[k]:.4f}",
                     f"{premium[k]:.2f}"])
    tab_path = write_table("O3_coordination_premium.csv",
                           ["phi", "harm_coordinated", "harm_independent", "premium"],
                           rows[1:])

    para = (
        f"O3: The coordination premium is ~1 (separable) below phi*~{phi_star}, then "
        f"rises steeply -- coordinated synchronization produces feeder harm that "
        f"diversified dispatch of the same units does not, because the shared thermal "
        f"limit only binds under synchronization. This mirrors the owner-side premium "
        f"rho. The premium exists ONLY above threshold, so the per-feeder cap (O1) and "
        f"the correlation detector (O6) remove it."
    )
    return {"phi_star": phi_star, "premium_max": float(premium.max()),
            "fig": fig_path, "table": tab_path, "paragraph": para}


if __name__ == "__main__":
    out = run()
    print(out["paragraph"])
    print("figure:", out["fig"])
