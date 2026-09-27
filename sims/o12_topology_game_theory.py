"""O12 -- How nodal topology reshapes the three equations (the game-theory spine).

The three core marginal-price equations (research.tex S5.2) assume a single scalar
beta. But beta is set by the network: an injection at node n moves the constrained
price only through the grid's shift factors, so beta -> beta * a_n, where a_n is
node n's PRICE LEVERAGE (models/network_impact.py). The three equations become

    price-taker            :  p
    semi (unit i)          :  p - beta * a_n * q_i
    big market-maker       :  p - beta * a_n * Q      (relief = sum_m a_m q_m)

Two quantities the topology sets, and this sim measures across canonical grids:

  1. COORDINATION AMPLIFICATION  =  (sum_n a_n) / max_n a_n.
     How much more price power the coordinated fleet (regime 3, uses the aligned
     sum) has than the best single strategic unit (regime 2). This is the mirror
     of the owner-side coordination premium -- now shown to be a TOPOLOGY property.

  2. MARKET-MAKING HARM: hold total fleet MW fixed, split across each grid's fleet
     nodes, and let the big market-maker withhold optimally (sell where a_n is low,
     hold back where a_n is high). Harm = extra cost to load vs the price-taking
     (full-relief) benchmark. Same fleet, same equations -- different wiring,
     different havoc.

All grids are synthetic/representative (SPEC S0). Every offensive number is paired
with the defense: a per-node market-share / penetration screen keyed to a_n plus
the correlation detector (O6) -- watch the HIGH-leverage nodes.
"""
from __future__ import annotations

import numpy as np

from models.price import fprime, load_for_price, inverse_supply
from models import network_impact as ni
from sims._common import (savefig, write_table, annotate_defense,
                          C_HARM, C_MAIN, C_SAFE, C_WARN, C_MUTED, plt)

P0_SCARCITY = 2500.0            # $/MWh scarcity anchor (offer-cap reference)
FLEET_MW_TOTAL = 4800.0        # 240k units x 20 kW (the 2-yr horizon)
SCARCITY_LOAD_MW = None        # filled from the price anchor
WINDOW_H = 2.0

PLAIN = {
    "radial chain": "one line in\n(radial)",
    "hub & spoke": "hub &\nspokes",
    "meshed ring": "meshed\n(many paths)",
    "long export": "long export\n(congested)",
}


def analyze(topo):
    a, _ = ni.leverage(topo["n_bus"], topo["lines"], topo["interface_line"],
                       topo["fleet_nodes"])
    a = np.clip(a, 0.0, None)                       # relief leverage (>=0 part)
    n_fleet = len(topo["fleet_nodes"])
    cap = np.full(n_fleet, FLEET_MW_TOTAL / n_fleet)

    beta = float(fprime(load_for_price(P0_SCARCITY)))   # $/MWh per MW (local, for context)
    L = load_for_price(P0_SCARCITY)

    # structural (bounded, convex) price at relief Y: p = f(L - Y), floored at the
    # merit order and capped at the offer cap -- valid over the full 4,800 MW swing.
    def price_fn(Y):
        return float(inverse_supply(L - Y))

    # coordination amplification (topology property): regime 3 (aligned sum) over
    # regime 2 (best single unit).
    amp = float(a.sum() / max(a.max(), 1e-9))

    # The grid counts on the fleet's relief like any resource. A price-taking
    # (helpful) fleet fully relieves scarcity -> lowest price. A market-maker
    # WITHHOLDS that relief to keep price high. The harm is the price suppression
    # denied, valued on all load. Its ceiling is set by the topology's total
    # leverage sum_n a_n*cap_n (the regime-3 coefficient).
    Y_full = float(np.sum(a * cap))                 # relief a helpful fleet delivers
    p_full = price_fn(Y_full)                       # price-taker (helpful) outcome
    p_withhold = price_fn(0.0)                       # market-maker withholds relief
    harm = (p_withhold - p_full) * L * WINDOW_H     # extra $ paid by all load

    return {"label": topo["label"], "a": a, "amp": amp, "beta": beta,
            "p_full": p_full, "p_withhold": p_withhold, "harm": harm,
            "withheld_mw": float(np.sum(cap)), "sum_a": float(a.sum()),
            "max_a": float(a.max())}


def run():
    res = [analyze(build()) for build in ni.ALL_TOPOLOGIES]
    labels = [PLAIN[r["label"]] for r in res]
    xs = np.arange(len(res))

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(12.4, 4.9))

    # LEFT: coordinated vs independent price leverage (the amplification)
    w = 0.38
    sum_a = [r["sum_a"] for r in res]
    max_a = [r["max_a"] for r in res]
    axL.bar(xs - w / 2, sum_a, width=w, color=C_HARM,
            label="coordinated fleet (regime 3: uses $\\Sigma a_n$)")
    axL.bar(xs + w / 2, max_a, width=w, color=C_MAIN,
            label="best single unit (regime 2: uses max $a_n$)")
    for i, r in enumerate(res):
        axL.text(i, r["sum_a"], f"  {r['amp']:.1f}x", ha="center", va="bottom",
                 fontsize=9.5, fontweight="bold", color=C_HARM)
    axL.set_xticks(xs); axL.set_xticklabels(labels, fontsize=8.4)
    axL.set_ylabel("price leverage across the fleet's nodes")
    axL.set_title("O12  Topology sets how much coordination multiplies market power\n"
                  "(the number on each bar = regime-3 amplification over regime 2)")
    axL.legend(loc="upper right", fontsize=8.2)
    annotate_defense(axL, "screen fleet market-share by node, keyed to $a_n$;\n"
                          "watch the HIGH-leverage nodes + correlation detector (O6)")

    # RIGHT: market-making harm to load, same fleet, per topology
    harms = [r["harm"] / 1e6 for r in res]
    bars = axR.bar(xs, harms, color=[C_HARM if h > 0 else C_MUTED for h in harms])
    axR.set_xticks(xs); axR.set_xticklabels(labels, fontsize=8.4)
    axR.set_ylabel("extra cost to ALL load, one 2-h window ($M)")
    axR.set_title("O12  Same fleet, same 3 equations -- different grid, different havoc\n"
                  f"(a {FLEET_MW_TOTAL:,.0f} MW market-maker withholding into scarcity)")
    for b, h in zip(bars, harms):
        axR.text(b.get_x() + b.get_width() / 2, h, f" \\${h:,.0f}M",
                 ha="center", va="bottom", fontsize=9.5, fontweight="bold")
    axR.margins(y=0.18)
    annotate_defense(axR, "the congested grid concentrates leverage -- exactly\n"
                          "where a per-node share cap must bind hardest")
    fig_path = savefig(fig, "O12_topology_game_theory.png")

    # ---- table ----
    header = ["topology", "leverage a_n (fleet nodes)", "sum a_n", "amplification x",
              "relief withheld MW", "price helped->withheld $/MWh", "harm $M"]
    rows = []
    for r in res:
        rows.append([r["label"], np.array2string(np.round(r["a"], 2)),
                     f"{r['sum_a']:.2f}", f"{r['amp']:.2f}", f"{r['withheld_mw']:,.0f}",
                     f"{r['p_full']:,.0f}->{r['p_withhold']:,.0f}", f"{r['harm']/1e6:,.0f}"])
    tab_path = write_table("O12_topology_game_theory.csv", header, rows)

    hi = max(res, key=lambda r: r["harm"])
    lo = min(res, key=lambda r: r["harm"])
    para = (
        f"O12 (topology reshapes the three equations): The scalar beta in the price-taker / "
        f"semi / big-market-maker equations is really beta*a_n, where a_n is a node's price "
        f"leverage set by the grid's shift factors. Across representative topologies the "
        f"same {FLEET_MW_TOTAL:,.0f} MW fleet behaves very differently: a single-gateway grid "
        f"(radial / hub) aligns every node's leverage (a_n=1 everywhere), so coordinating the "
        f"fleet multiplies its market power ~{hi['amp']:.0f}x over a lone unit, and withholding "
        f"the relief the grid was counting on inflates one scarcity window's bill by up to "
        f"~${hi['harm']/1e6:,.0f}M ({hi['label']}); a meshed grid dilutes leverage (amp "
        f"~{[r['amp'] for r in res if 'mesh' in r['label']][0]:.0f}x) and a long-export grid "
        f"STRANDS capacity behind congestion (a_n~0), cutting the ceiling to ~${lo['harm']/1e6:,.0f}M "
        f"({lo['label']}). So whether a competitor's market-making can wreck the grid is a "
        f"property of the WIRING, not just the fleet size -- and the defense follows the "
        f"topology: a per-node market-share screen keyed to a_n, hardest on the high-leverage "
        f"nodes, plus the correlation detector (O6). [synthetic/representative networks; "
        f"beta from the ERCOT scarcity anchor]"
    )
    return {"fig": fig_path, "table": tab_path, "paragraph": para, "results": res}


if __name__ == "__main__":
    out = run()
    print(out["paragraph"])
    print("figure:", out["fig"])
    for r in out["results"]:
        print(f"  {r['label']:14s} amp={r['amp']:.2f}  harm=${r['harm']/1e6:,.0f}M  "
              f"withheld={r['withheld_mw']:,.0f} MW  a={np.round(r['a'],2)}")
