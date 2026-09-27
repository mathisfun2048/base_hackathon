"""O11b -- Watch one neighborhood overload (the picture anyone can read).

The bar chart (O11) says "~140 units overload a suburban block." This draws the
block itself and colors every wire by how loaded it is (green = fine, red = over
its limit) as more battery homes act in lockstep.

The real, legible lesson it makes visible: each HOME's own little service wire
stays green -- no single house is the problem. The wire that overloads is the
SHARED one feeding the whole block. So the danger is concentration + coordination
on a shared wire, not any one battery. That is exactly the paper's G1 story:
the shared limit only binds when many co-located units act together.

Same physics as O1/O11 (LinDistFlow feasibility); this module only VISUALIZES it.
The feeder is synthetic/representative (SPEC S0) -- no real circuit is drawn.

DEFENSE (paired): cap how many co-located homes may act together (per-feeder
penetration cap) + a synchronized-dispatch interlock on the shared wire.
"""
from __future__ import annotations

import numpy as np
import matplotlib as mpl

from data.topology import RadialFeeder, _build_children
from models import feasibility
from sims._common import FIG_DIR, C_HARM, C_SAFE, C_MUTED, plt
import os

UNIT_MW = 0.020        # 20 kW


def neighborhood_feeder():
    """A synthetic branching feeder that reads like a neighborhood: a main street
    (well-rated trunk) with side-street laterals; ONE block is the battery cluster,
    fed by a single shared 3 MVA wire. Homes hang off on their own small drops."""
    V_base = 12.47
    Z = V_base ** 2
    parent, seg, Srate, d = [-1], [0.0], [12.0], [0.0]

    def add(par, seglen, rating, dem):
        parent.append(par); seg.append(seglen); Srate.append(rating); d.append(dem)
        return len(parent) - 1

    # main street (trunk): well rated, stays green
    trunk = [0]
    for _ in range(5):
        trunk.append(add(trunk[-1], 0.15, 10.0, 0.03))

    # two "context" side streets (a few ordinary homes; not batteries)
    for t in (trunk[1], trunk[4]):
        b = add(t, 0.10, 4.0, 0.02)
        for _ in range(3):
            add(b, 0.04, 0.6, 0.03)

    # THE battery block: one shared feeding wire (3 MVA) -> a small block spine
    # -> homes on their own drops. Overload will appear on the shared wire.
    block_feed = add(trunk[3], 0.12, 3.0, 0.02)          # the shared wire
    spine = [block_feed]
    for _ in range(3):
        spine.append(add(spine[-1], 0.05, 2.5, 0.02))
    block_homes = []
    for s in spine:
        for _ in range(3):
            block_homes.append(add(s, 0.03, 0.8, 0.02))   # each home's own drop

    parent = np.array(parent, int); seg = np.array(seg, float)
    Srate = np.array(Srate, float); d = np.array(d, float)
    fdr = RadialFeeder(parent=parent, r=seg * 0.33 / Z, x=seg * 0.38 / Z,
                       Srate=Srate, d=d, coloc_node=block_homes[0],
                       name="representative-neighborhood",
                       provenance="synthetic; 12.47 kV class, representative")
    fdr.children = _build_children(parent)
    return fdr, block_homes, block_feed


def tree_layout(fdr):
    depth, ypos, counter = {0: 0}, {}, [0]

    def dfs(u, dp):
        depth[u] = dp
        kids = fdr.children.get(u, [])
        if not kids:
            ypos[u] = counter[0]; counter[0] += 1
        else:
            for c in kids:
                dfs(c, dp + 1)
            ypos[u] = float(np.mean([ypos[c] for c in kids]))

    dfs(0, 0)
    return {n: (depth[n], ypos[n]) for n in range(fdr.N)}


def draw(ax, fdr, block_homes, phi, pos, cmap, norm):
    """Distribute phi battery homes across the block; color wires by loading."""
    q = np.zeros(fdr.N)
    per = phi / len(block_homes)
    for h in block_homes:
        q[h] = -per * UNIT_MW                     # all charging together (added load)
    P_edge, R_edge = feasibility.branch_flows(fdr, q)
    K = feasibility.thermal_limits(fdr, R_edge)
    K[0] = fdr.Srate[0]
    load = np.abs(P_edge) / np.clip(K, 1e-6, None)

    over = False
    for n in range(1, fdr.N):
        p = int(fdr.parent[n]); x0, y0 = pos[p]; x1, y1 = pos[n]
        frac = float(load[n]); over = over or frac > 1.0
        ax.plot([x0, x1], [y0, y1], color=cmap(norm(frac)),
                lw=1.3 + 4.0 * min(frac, 1.2), solid_capstyle="round", zorder=1)

    # ordinary homes (grey), battery homes (blue squares), substation (black)
    others = [n for n in range(1, fdr.N) if not fdr.children.get(n) and n not in block_homes]
    ax.scatter([pos[n][0] for n in others], [pos[n][1] for n in others],
               s=16, color=C_MUTED, zorder=2)
    ax.scatter([pos[n][0] for n in block_homes], [pos[n][1] for n in block_homes],
               s=34, marker="s", color="#1f77b4", zorder=3)
    ax.scatter([pos[0][0]], [pos[0][1]], marker="s", s=150, color="#222", zorder=4)
    ax.annotate("substation", pos[0], textcoords="offset points", xytext=(2, 12),
                ha="center", fontsize=8, color="#222")

    # label the shared wire's loading
    peak = float(load[1:].max())
    ax.annotate(f"{phi} battery homes", (np.mean([pos[h][0] for h in block_homes]),
                max(pos[h][1] for h in block_homes) + 0.7),
                ha="center", fontsize=9, color="#1f77b4", fontweight="bold")
    ax.set_title(f"shared wire at {peak*100:.0f}% of its limit"
                 + ("   -- OVERLOAD" if over else "   -- ok"),
                 fontsize=10.5, color=C_HARM if over else C_SAFE)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)


def run():
    fdr, block_homes, block_feed = neighborhood_feeder()
    pos = tree_layout(fdr)
    cmap, norm = mpl.cm.RdYlGn_r, mpl.colors.Normalize(0.0, 1.2)

    fig, axes = plt.subplots(1, 3, figsize=(13.6, 5.0), constrained_layout=True)
    for ax, phi in zip(axes, [50, 150, 240]):
        draw(ax, fdr, block_homes, phi, pos, cmap, norm)

    sm = mpl.cm.ScalarMappable(cmap=cmap, norm=norm)
    cbar = fig.colorbar(sm, ax=axes, orientation="horizontal", fraction=0.05, pad=0.02)
    cbar.set_label("wire loading (share of its limit)  --  each HOME's own drop stays green; "
                   "the SHARED wire is what overloads")
    cbar.set_ticks([0, 0.5, 1.0, 1.2])
    cbar.set_ticklabels(["0%", "50%", "100% (limit)", ">120%"])

    fig.suptitle("O11b  One block, more battery homes acting together: no single home "
                 "is the problem -- the SHARED wire feeding the block overloads\n"
                 "DEFENSE: cap how many co-located homes may act in lockstep + "
                 "synchronized-dispatch interlock   (representative/synthetic feeder -- no real circuit)",
                 fontsize=10.5)
    path = os.path.join(FIG_DIR, "O11b_feeder_map.png")
    fig.savefig(path, bbox_inches="tight", dpi=130)
    plt.close(fig)

    para = ("O11b (neighborhood map): the suburban block from O11, drawn. As more battery "
            "homes act in lockstep the color climbs from green to red -- but the overload "
            "lands on the single SHARED wire feeding the block, while each home's own drop "
            "stays green. The danger is concentration + coordination on a shared wire, not "
            "any one battery. DEFENSE: per-feeder penetration cap + synchronized-dispatch "
            "interlock. [representative/synthetic feeder]")
    return {"fig": path, "paragraph": para}


if __name__ == "__main__":
    out = run()
    print(out["paragraph"])
    print("figure:", out["fig"])
