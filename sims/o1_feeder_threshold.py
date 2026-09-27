"""O1 -- Local physical threshold phi* (SPEC S2).

Sweep co-located unit count phi on a representative radial feeder; find phi*
where synchronized charge/discharge first violates a thermal or voltage limit
(the joint-feasibility set A_t). Report units-per-feeder relative to the feeding
transformer/segment rating. Expected O(1e2), NOT O(1e4) -- the honest answer to
"how many nodes to crash [locally]".

DEFENSE paired with the result: a per-feeder penetration cap set below phi*
(with margin), plus a synchronized-dispatch interlock at the concentration node.
"""
from __future__ import annotations

import numpy as np

from data.topology import representative_feeder
from models import feasibility
from models.degradation import UNIT_KW
from sims._common import savefig, write_table, annotate_defense, C_HARM, C_MAIN, C_SAFE, plt


def run(unit_kw: float = UNIT_KW, phi_max: int = 400):
    fdr = representative_feeder()
    node = fdr.coloc_node
    unit_mw = unit_kw / 1000.0

    phis = np.arange(0, phi_max + 1)
    over_dis = np.zeros_like(phis, dtype=float)   # discharge (reverse flow)
    over_chg = np.zeros_like(phis, dtype=float)   # charge (forward flow)
    vmax_dis = np.zeros_like(phis, dtype=float)
    vmin_chg = np.zeros_like(phis, dtype=float)

    for k, phi in enumerate(phis):
        mw = phi * unit_mw
        vd = feasibility.violations(fdr, feasibility.inject_at(fdr, node, +mw))
        vc = feasibility.violations(fdr, feasibility.inject_at(fdr, node, -mw))
        over_dis[k] = vd["thermal_overload_MW"] + vd["v_high"] + vd["v_low"]
        over_chg[k] = vc["thermal_overload_MW"] + vc["v_high"] + vc["v_low"]
        vmax_dis[k] = vd["v_max"]
        vmin_chg[k] = vc["v_min"]

    def first_violation(fdr, node, unit_mw, sign):
        for phi in phis:
            v = feasibility.violations(fdr, feasibility.inject_at(fdr, node, sign * phi * unit_mw))
            if v["any"]:
                cause = "thermal" if v["any_thermal"] else "voltage"
                return int(phi), cause, v
        return None, None, None

    phi_dis, cause_dis, vd_star = first_violation(fdr, node, unit_mw, +1)
    phi_chg, cause_chg, vc_star = first_violation(fdr, node, unit_mw, -1)
    phi_star = min([p for p in (phi_dis, phi_chg) if p is not None], default=None)

    # ---- figure ----
    fig, ax = plt.subplots()
    ax.plot(phis, over_dis, color=C_HARM, label="synchronized discharge (reverse flow)")
    ax.plot(phis, over_chg, color=C_MAIN, label="synchronized charge (added load)")
    ax.set_xlabel("co-located units at one concentration node,  $\\varphi$")
    ax.set_ylabel("constraint-violation magnitude (MW + pu)")
    ax.set_title(f"O1  Local concentration threshold on {fdr.name}\n"
                 f"20 kW units; feeding segment rated {fdr.Srate[node]:.1f} MVA, "
                 f"{len(fdr.path_to_root(node))} edges deep")
    if phi_star is not None:
        ax.axvline(phi_star, color=C_SAFE, ls="--", lw=1.4)
        ax.annotate(f"$\\varphi^*$ = {phi_star} units\n({phi_star*unit_kw/1000:.1f} MW, "
                    f"{cause_dis if phi_dis==phi_star else cause_chg}-bound)",
                    xy=(phi_star, 0), xytext=(phi_star + 12, over_dis.max() * 0.5),
                    color=C_SAFE, fontsize=9,
                    arrowprops=dict(arrowstyle="->", color=C_SAFE))
    ax.legend(loc="upper left")
    annotate_defense(ax, f"per-feeder cap ~ {int(phi_star*0.7)} units at any node "
                          f"(0.7 x phi*); synchronized-dispatch interlock")
    fig_path = savefig(fig, "O1_feeder_threshold.png")

    # ---- table ----
    rows = [
        ["feeder", fdr.name],
        ["provenance", fdr.provenance],
        ["concentration node", node],
        ["edges to substation", len(fdr.path_to_root(node))],
        ["feeding segment rating (MVA)", f"{fdr.Srate[node]:.2f}"],
        ["unit power (kW)", f"{unit_kw:.0f}"],
        ["phi* discharge (units)", phi_dis],
        ["phi* discharge cause", cause_dis],
        ["phi* charge (units)", phi_chg],
        ["phi* charge cause", cause_chg],
        ["phi* (binding, units)", phi_star],
        ["phi* aggregate (MW)", f"{phi_star*unit_kw/1000:.2f}" if phi_star else "n/a"],
        ["recommended per-feeder cap (units)", int(phi_star * 0.7) if phi_star else "n/a"],
    ]
    tab_path = write_table("O1_feeder_threshold.csv", ["quantity", "value"], rows)

    para = (
        f"O1: On the representative radial feeder, {phi_star} synchronized 20 kW units "
        f"({phi_star*unit_kw/1000:.1f} MW) at one concentration node first violate a "
        f"{cause_dis if phi_dis==phi_star else cause_chg} limit -- O(1e2), not O(1e4). "
        f"The local threat is feeder concentration, and it is capped by a per-feeder "
        f"penetration limit (~{int(phi_star*0.7)} units) plus a synchronized-dispatch "
        f"interlock at the concentration node."
    )
    return {"phi_star": phi_star, "phi_dis": phi_dis, "phi_chg": phi_chg,
            "cause_dis": cause_dis, "cause_chg": cause_chg,
            "fig": fig_path, "table": tab_path, "paragraph": para}


if __name__ == "__main__":
    out = run()
    print(out["paragraph"])
    print("figure:", out["fig"])
    print("table :", out["table"])
