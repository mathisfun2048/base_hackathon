"""O7 -- How many nodes to crash the SYSTEM / MARKET (SPEC S1/S2; user Q1,Q2).

"Crash" is defined physically as ROLLING BLACKOUTS: ERCOT Energy Emergency Alert
Level 3 (EEA3), when Physical Responsive Capability (PRC) falls to <=1,430 MW and
ERCOT sheds firm load. The number of coordinated nodes required depends entirely
on the STARTING reserve, so we anchor to REAL ERCOT PRC data (today) plus
documented stress events (Winter Storm Uri 2021, Summer-heat EEA2 2023) and use a
p95-tail (tight-reserve) view.

Per-node PRC impact of a coordinated withdrawal:
  * conservative: a node charging adds 20 kW of load            -> 0.02 MW/node
  * full swing:   a node expected to DISCHARGE (+20 kW support) flips to CHARGE
                  (-20 kW) -> 40 kW net PRC swing                -> 0.04 MW/node
Fleet = 20,000 nodes => 400 MW (conservative) to 800 MW (full swing).

Headline finding: on a healthy grid it takes O(1e5) nodes (5-40x the actual
fleet) -- the fleet CANNOT crash the system. But on an already-critical grid
(EEA1-EEA2, which really occurred on 2023-09-06 and during Uri), a fully
coordinated 400-800 MW swing IS enough to cross into rolling blackouts. The real
threat is AMPLIFICATION of already-stressed intervals, not cold-start collapse.

DEFENSE (paired): a firmware/operational rule that forbids coordinated CHARGING
during EEA / low-PRC conditions (batteries must support, never withdraw), plus
the per-feeder penetration cap (O1) and the cross-unit correlation detector (O6).
The market-price "crash" panel shows prices pin at the offer cap under scarcity
regardless of the fleet -- the fleet's own marginal price impact is bounded (O2).
"""
from __future__ import annotations

import numpy as np

from data.fetch_ercot import (fetch_prc, EEA_THRESHOLDS, DOCUMENTED_EVENTS,
                              ROLLING_BLACKOUT_PRC, find_stressed_interval)
from models.price import fprime, load_for_price, OFFER_CAP
from sims._common import (savefig, write_table, annotate_defense,
                          C_HARM, C_MAIN, C_SAFE, C_WARN, C_MUTED, plt)

UNIT_KW = 20.0
FLEET_NODES = 20_000
PER_NODE_CONSERVATIVE = 0.020   # MW (charge = added load)
PER_NODE_SWING = 0.040          # MW (discharge-support -> charge)


def nodes_to_eea3(prc_start, per_node_mw):
    return max((prc_start - ROLLING_BLACKOUT_PRC) / per_node_mw, 0.0)


def run():
    # ---- real reserve data ----
    try:
        prc = fetch_prc()
        prc_real = True
    except Exception as exc:
        prc = {"current_prc_mw": float("nan"), "today_min_mw": 9231.0,
               "today_p5_mw": 10277.0, "today_median_mw": 17338.0,
               "date": "unavailable", "source": f"PRC unavailable ({type(exc).__name__})"}
        prc_real = False

    # ---- anchor conditions: real (today) + documented events + EEA thresholds ----
    anchors = [
        ("Today median (REAL)", prc["today_median_mw"], "real"),
        ("Today minimum (REAL)", prc["today_min_mw"], "real"),
        ("EEA Watch", EEA_THRESHOLDS["EEA Watch"], "threshold"),
        ("EEA1", EEA_THRESHOLDS["EEA1"], "threshold"),
        ("EEA2 = Summer 2023-09-06 (documented)", EEA_THRESHOLDS["EEA2"], "event"),
        ("EEA1 crossover (fleet full-swing)", ROLLING_BLACKOUT_PRC + FLEET_NODES * PER_NODE_SWING, "derived"),
    ]

    rows = []
    for name, p0, kind in anchors:
        n_cons = nodes_to_eea3(p0, PER_NODE_CONSERVATIVE)
        n_swing = nodes_to_eea3(p0, PER_NODE_SWING)
        fleet_ok = (n_swing <= FLEET_NODES) or (n_cons <= FLEET_NODES)
        rows.append([name, f"{p0:.0f}", f"{n_swing:.0f}", f"{n_cons:.0f}",
                     f"{n_swing/FLEET_NODES:.2f}x-{n_cons/FLEET_NODES:.2f}x",
                     "YES" if fleet_ok else "no"])

    # crossover PRC below which the whole fleet alone can trigger EEA3
    cross_swing = ROLLING_BLACKOUT_PRC + FLEET_NODES * PER_NODE_SWING   # ~2230 (~EEA1)
    cross_cons = ROLLING_BLACKOUT_PRC + FLEET_NODES * PER_NODE_CONSERVATIVE  # ~1830 (~EEA2)

    # ---- market (price) crash panel: nodes to drive price to the offer cap ----
    stressed, _ = find_stressed_interval()
    p0_grid = np.linspace(150.0, OFFER_CAP * 0.97, 60)
    nodes_to_cap = []
    for p0 in p0_grid:
        L0 = load_for_price(p0)
        beta = float(fprime(L0))
        dQ = (OFFER_CAP - p0) / max(beta, 1e-9)     # MW to lift price to cap
        nodes_to_cap.append(dQ / PER_NODE_CONSERVATIVE)
    nodes_to_cap = np.array(nodes_to_cap)

    # ---- figure ----
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(12.0, 4.8))

    # LEFT: nodes to rolling blackout vs starting reserve
    prc_grid = np.linspace(ROLLING_BLACKOUT_PRC + 20, 18_000, 400)
    axL.plot(prc_grid, [nodes_to_eea3(p, PER_NODE_SWING) for p in prc_grid],
             color=C_HARM, lw=2.2, label="nodes @ 40 kW full swing")
    axL.plot(prc_grid, [nodes_to_eea3(p, PER_NODE_CONSERVATIVE) for p in prc_grid],
             color=C_WARN, lw=2.0, ls="--", label="nodes @ 20 kW added load")
    axL.axhline(FLEET_NODES, color=C_MAIN, lw=1.6, ls=":", label="actual fleet = 20,000 nodes")
    axL.set_yscale("log")
    axL.set_xlabel("starting reserve PRC (MW)  --  lower = more stressed")
    axL.set_ylabel("coordinated nodes to reach EEA3 (rolling blackouts)")
    axL.set_title("O7  Nodes to crash the SYSTEM vs starting reserve\n"
                  "(crash = EEA3 firm load shed, PRC $\\leq$ 1,430 MW)")
    # markers
    for x, lab, col in [
        (prc["today_min_mw"], "today min (REAL)", C_SAFE),
        (EEA_THRESHOLDS["EEA1"], "EEA1", C_MUTED),
        (EEA_THRESHOLDS["EEA2"], "EEA2 (Sep-2023)", C_MUTED),
    ]:
        axL.axvline(x, color=col, lw=1.0, ls="-", alpha=0.6)
        axL.text(x, axL.get_ylim()[1] * 0.5, " " + lab, rotation=90,
                 fontsize=7.5, color=col, va="top")
    # shade region where fleet alone suffices
    axL.axvspan(ROLLING_BLACKOUT_PRC, cross_swing, color=C_HARM, alpha=0.08)
    axL.text(cross_swing, FLEET_NODES * 2.2,
             f"  fleet alone can tip\n  below PRC~{cross_swing:,.0f} MW", fontsize=8,
             color=C_HARM, va="bottom")
    axL.legend(loc="upper left", fontsize=8.2)
    annotate_defense(axL, "block coordinated CHARGING during EEA/low-PRC\n"
                          "(support, never withdraw) + caps (O1) + detector (O6)")

    # RIGHT: market/price crash
    axR.plot(p0_grid, nodes_to_cap, color=C_HARM, lw=2.2,
             label="nodes to drive price to $5,000 cap")
    axR.axhline(FLEET_NODES, color=C_MAIN, lw=1.6, ls=":", label="actual fleet = 20,000 nodes")
    axR.set_yscale("log")
    axR.set_xlabel("starting price on a stressed interval ($/MWh)")
    axR.set_ylabel("coordinated nodes to reach the offer cap")
    axR.set_title("O7  Nodes to crash the MARKET (price to cap)\n"
                  "scarcity itself pins price at the cap; fleet impact is bounded (O2)")
    axR.legend(loc="upper right", fontsize=8.2)
    annotate_defense(axR, "monitor scarcity intervals; correlation detector (O6)")
    fig_path = savefig(fig, "O7_system_crash.png")

    # ---- table ----
    header = ["grid condition", "start PRC (MW)", "nodes @40kW swing",
              "nodes @20kW load", "x fleet (swing-load)", "fleet alone?"]
    tab_path = write_table("O7_system_crash.csv", header, rows)

    # summary numbers for the paragraph
    n_eea2_swing = nodes_to_eea3(EEA_THRESHOLDS["EEA2"], PER_NODE_SWING)
    n_min_swing = nodes_to_eea3(prc["today_min_mw"], PER_NODE_SWING)

    para = (
        f"O7 (nodes to crash the system): Defining a crash as EEA3 rolling blackouts "
        f"(PRC<=1,430 MW), the number of coordinated 20 kW nodes required depends on the "
        f"starting reserve. On today's REAL grid (min PRC {prc['today_min_mw']:,.0f} MW) "
        f"it takes ~{n_min_swing:,.0f} nodes -- ~{n_min_swing/FLEET_NODES:.0f}x the entire "
        f"20,000-unit fleet -- so the fleet CANNOT crash a healthy system. But on an "
        f"already-critical grid at EEA2 ({EEA_THRESHOLDS['EEA2']:,.0f} MW, as on 2023-09-06), "
        f"only ~{n_eea2_swing:,.0f} nodes ({n_eea2_swing/FLEET_NODES:.0%} of the fleet) are "
        f"enough to tip into rolling blackouts; during Winter Storm Uri the grid was already "
        f"in EEA3. The fleet becomes a marginal trigger only when reserves are already below "
        f"~{cross_swing:,.0f} MW (~EEA1). Market 'crash' is bounded too: scarcity pricing "
        f"pins the price at the $5,000 cap on its own, and the fleet's own price impact is "
        f"limited (O2). Real threat = amplification of already-stressed intervals. "
        f"DEFENSE: forbid coordinated charging during EEA/low-PRC, plus per-feeder caps (O1) "
        f"and the correlation detector (O6)."
        + ("" if prc_real else " [PRC data unavailable; used cached/reference reserves]")
    )
    return {"fig": fig_path, "table": tab_path, "paragraph": para,
            "crossover_prc_swing": cross_swing, "crossover_prc_cons": cross_cons,
            "nodes_eea2_swing": n_eea2_swing, "prc_real": prc_real,
            "prc_source": prc["source"]}


if __name__ == "__main__":
    out = run()
    print(out["paragraph"])
    print("figure:", out["fig"])
    print("table :", out["table"])
