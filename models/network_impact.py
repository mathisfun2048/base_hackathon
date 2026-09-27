"""Nodal price-impact from topology -- how the grid's wiring reshapes beta.

This is the game-theoretic topology extension the analysis was missing. The three
core marginal-price equations in research.tex (S5.2, eq:marginals) assume a SINGLE
scalar price-impact slope beta:

    price-taker            :  p
    semi (strategic unit i):  p - beta * q_i
    big market-maker       :  p - beta * Q

But beta is not a constant -- it is set by the network. In a real (locational)
market the price at the constrained/scarcity point responds to an injection at
node n only through the network's shift factors. Define node n's PRICE LEVERAGE

    a_n = (how much an injection at n relieves the binding interface)
        = normalized shift factor of node n onto the congested line l*.

Then the scalar beta becomes beta * a_n, and the three equations become

    price-taker            :  p
    semi (unit i at node n):  p - beta * a_n * q_i
    big market-maker       :  p - beta * a_n * Q          (relief uses sum_m a_m q_m)

a_n is pure topology. This module computes it from the DC shift factors (PTDF) of
a small representative network -- standard power-systems linear algebra, no LP:

    PTDF = Bline @ inv(Bbus_reduced)          (injection withdrawn at the slack)

The consequence the market-maker exploits is immediate and is the punchline:
WITHHOLD where leverage is high (big a_n), SELL where it is low. How much total
leverage exists, and whether coordinating across nodes amplifies it, is a property
of the topology -- which is exactly "topology changes the game."

All networks here are SYNTHETIC / representative (SPEC S0). No real circuit.
"""
from __future__ import annotations

import numpy as np


def ptdf(n_bus: int, lines, slack: int = 0) -> np.ndarray:
    """DC power transfer distribution factors.

    lines: list of (i, j, x) with per-unit reactance x on edge i->j.
    Returns PTDF (L x n_bus): PTDF[l, n] = sensitivity of real flow on line l to a
    1 MW injection at bus n withdrawn at the slack bus. Standard DC formulation.
    """
    L = len(lines)
    b = np.array([1.0 / x for (_i, _j, x) in lines], dtype=float)
    A = np.zeros((L, n_bus))
    for k, (i, j, _x) in enumerate(lines):
        A[k, i] += 1.0
        A[k, j] -= 1.0
    Bline = np.diag(b) @ A                       # flow = Bline @ theta
    Bbus = A.T @ np.diag(b) @ A                  # nodal susceptance (weighted Laplacian)
    keep = [n for n in range(n_bus) if n != slack]
    Bred_inv = np.linalg.inv(Bbus[np.ix_(keep, keep)])
    P = np.zeros((L, n_bus))
    P[:, keep] = Bline[:, keep] @ Bred_inv       # slack column stays 0
    return P


def leverage(n_bus, lines, interface_line: int, fleet_nodes, slack: int = 0):
    """Price leverage a_n for each fleet node, from the topology.

    interface_line: index into `lines` of the congested line l* that sets the
    scarcity price (relieving it lowers the price). a_n is the shift factor of node
    n onto l*, oriented so that a_n > 0 means 'injecting here relieves the
    constraint' (has price-lowering / withholding-raising leverage), and normalized
    so the most-leveraged fleet node is 1.0.
    """
    P = ptdf(n_bus, lines, slack=slack)
    row = P[interface_line]                      # sensitivity of l* to each node
    # base flow on l* is an import INTO the scarcity zone; an injection that
    # reduces that flow relieves scarcity. Orient by the sign of the reference
    # flow direction (from-bus -> to-bus is the import direction here).
    a_raw = -row                                 # relief = reduce line flow
    a_fleet = np.array([a_raw[n] for n in fleet_nodes], dtype=float)
    scale = np.max(np.abs(a_fleet)) if np.max(np.abs(a_fleet)) > 0 else 1.0
    return a_fleet / scale, a_raw


def regime_marginals(p, beta, a_n, q_i, Q):
    """The three core equations, now topology-aware (per node n).

    Returns the marginal-price term each regime internalizes at a node with
    leverage a_n: (taker, semi, central). Reduces to research.tex's scalar
    equations when a_n = 1.
    """
    return p, p - beta * a_n * q_i, p - beta * a_n * Q


def market_maker_dispatch(a, cap, price_fn):
    """Big market-maker (regime 3) optimal dispatch across leveraged nodes.

    Maximizes fleet profit  Pi = price(Y) * Q  with  Y = sum_n a_n q_n (effective
    relief that lowers price) and Q = sum_n q_n (energy sold), subject to
    0 <= q_n <= cap_n (discharge-only -- the legal scarcity action; the compromised
    charge-into-scarcity tail is O10). `price_fn(Y)` is the (bounded, convex)
    structural price at relief Y, so prices stay between the merit floor and the
    offer cap.

    Marginal value of q_n is  price(Y) + Q*price'(Y)*a_n : since price'(Y) < 0,
    SELL where leverage a_n is low, WITHHOLD where a_n is high. The optimum
    therefore discharges nodes in increasing order of a_n; we sweep that frontier.
    Returns dict with q*, Y, Q, price, profit.
    """
    a = np.asarray(a, float)
    cap = np.asarray(cap, float)
    order = np.argsort(a)                       # discharge lowest-leverage first
    best = None
    for k in range(len(a) + 1):
        q = np.zeros(len(a))
        q[order[:k]] = cap[order[:k]]
        Y = float(np.sum(a * q)); Q = float(np.sum(q))
        price = float(price_fn(Y)); profit = price * Q
        if best is None or profit > best["profit"]:
            best = {"q": q.copy(), "Y": Y, "Q": Q, "price": price, "profit": profit}
    return best


# ---------------------------------------------------------------------------
# Canonical representative topologies (synthetic). Each returns:
#   n_bus, lines[(i,j,x)], interface_line, fleet_nodes, load_node, label
# The interface line is the one whose congestion prices scarcity.
# ---------------------------------------------------------------------------
def topo_radial_chain():
    """Generators at the slack, load far down a single radial line. One path in,
    so every fleet node's relief funnels through the same interface -> leverage
    is high and ALIGNED (coordination amplifies)."""
    lines = [(0, 1, 0.05), (1, 2, 0.05), (2, 3, 0.05), (3, 4, 0.05)]
    return dict(n_bus=5, lines=lines, interface_line=0,
                fleet_nodes=[1, 2, 3, 4], load_node=4, label="radial chain")


def topo_hub_spoke():
    """A strong hub feeding load spokes. Fleet on the spokes; each reaches the
    priced interface directly but independently."""
    lines = [(0, 1, 0.04),           # slack -> hub (the interface)
             (1, 2, 0.06), (1, 3, 0.06), (1, 4, 0.06), (1, 5, 0.06)]
    return dict(n_bus=6, lines=lines, interface_line=0,
                fleet_nodes=[2, 3, 4, 5], load_node=1, label="hub & spoke")


def topo_mesh_ring():
    """A meshed ring: multiple parallel paths to the load, so an injection's
    effect splits across lines -> leverage on any single interface is DILUTED."""
    lines = [(0, 1, 0.06), (1, 2, 0.06), (2, 3, 0.06), (3, 4, 0.06),
             (4, 0, 0.06), (1, 3, 0.06)]     # ring + a chord = multiple paths
    return dict(n_bus=5, lines=lines, interface_line=0,
                fleet_nodes=[1, 2, 3, 4], load_node=3, label="meshed ring")


def topo_long_export():
    """Texas-like: a generation zone behind a long, congestion-limited export
    line, and a load/scarcity zone. Fleet split across both sides -> some nodes
    are stranded behind congestion (a_n ~ 0), some sit at the scarcity zone
    (a_n ~ 1). Topology decides which capacity has price power."""
    lines = [(0, 1, 0.03),            # gen zone internal
             (1, 2, 0.20),            # long export interface (congested)
             (2, 3, 0.03), (2, 4, 0.03)]   # load zone internal
    return dict(n_bus=5, lines=lines, interface_line=1,
                fleet_nodes=[1, 3, 4], load_node=2, label="long export")


ALL_TOPOLOGIES = [topo_radial_chain, topo_hub_spoke, topo_mesh_ring, topo_long_export]


if __name__ == "__main__":
    for build in ALL_TOPOLOGIES:
        t = build()
        a, a_raw = leverage(t["n_bus"], t["lines"], t["interface_line"],
                            t["fleet_nodes"])
        print(f"{t['label']:14s}  fleet nodes {t['fleet_nodes']}  "
              f"leverage a_n = {np.round(a, 3)}  (sum={a.sum():.2f})")
