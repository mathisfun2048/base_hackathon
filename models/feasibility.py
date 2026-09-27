"""LinDistFlow feasibility on a radial feeder -- the set A_t (SPEC S4, O1).

Implements the paper's linearized flow (research.tex S3.1-3.2):

    P_et = sum_{k in down(n)} d_kt  -  sum_{i: n(i) in down(n)} q_it     (eq:flow)
    v_nt = v_0t - (2/S_base) * sum_{e in path(0->n)} (r_e P_et + x_e R_et) (eq:voltage)

with thermal and voltage constraints

    |P_et| <= K_et,  K_et = sqrt(Sbar_e^2 - R_et^2)                     (eq:thermal)
    Vmin^2 <= v_nt <= Vmax^2                                            (eq:voltagebounds)

`violations()` returns which constraints bind/break for a joint injection vector
q (MW, + = discharge/inject). This is what O1 sweeps to locate phi*, and what
O3's stress objective sums.

Scope caveat (verbatim intent from the paper): this certifies feasibility only
within the balanced, linearized model. It does NOT certify full unbalanced AC
power flow, protection coordination, or transient response.
"""
from __future__ import annotations

import numpy as np
from data.topology import RadialFeeder


def _reactive_demand(feeder: RadialFeeder) -> np.ndarray:
    """Fixed reactive demand per node (MVAr) from the lagging power factor."""
    tan_phi = np.tan(np.arccos(np.clip(feeder.pf, 1e-3, 1.0)))
    return feeder.d * tan_phi


def branch_flows(feeder: RadialFeeder, q: np.ndarray):
    """Real (P) and reactive (R) branch flow on every edge, in MW / MVAr.

    P_edge[n] and R_edge[n] are the flows on the edge parent[n] -> n, computed
    as the net downstream (demand - injection). Batteries inject real power only.
    """
    q = np.asarray(q, dtype=float)
    d = feeder.d
    dq = _reactive_demand(feeder)

    P_edge = np.zeros(feeder.N)
    R_edge = np.zeros(feeder.N)
    # post-order: accumulate subtree net demand upward
    net_p = d - q          # per-node net real draw (demand minus injection)
    net_q = dq.copy()      # per-node net reactive draw
    sub_p = net_p.copy()
    sub_r = net_q.copy()
    for n in feeder.subtree_order():      # children before parents
        if n == 0:
            continue
        p = int(feeder.parent[n])
        sub_p[p] += sub_p[n]
        sub_r[p] += sub_r[n]
        P_edge[n] = sub_p[n]
        R_edge[n] = sub_r[n]
    return P_edge, R_edge


def voltages(feeder: RadialFeeder, P_edge: np.ndarray, R_edge: np.ndarray):
    """Squared per-unit voltages v_n via the LinDistFlow drop equation."""
    v = np.full(feeder.N, feeder.v0, dtype=float)
    # BFS from root so parents computed before children
    order = feeder.subtree_order()[::-1]   # reverse post-order = top-down
    for n in order:
        if n == 0:
            continue
        p = int(feeder.parent[n])
        # per-unit: r,x already per-unit on S_base; P,R in MW/MVAr -> /S_base
        dv = 2.0 * (feeder.r[n] * P_edge[n] + feeder.x[n] * R_edge[n]) / feeder.S_base
        v[n] = v[p] - dv
    return v


def thermal_limits(feeder: RadialFeeder, R_edge: np.ndarray) -> np.ndarray:
    """K_e = sqrt(Sbar_e^2 - R_e^2), the real-power thermal envelope per edge."""
    inside = feeder.Srate ** 2 - R_edge ** 2
    return np.sqrt(np.clip(inside, 0.0, None))


def violations(feeder: RadialFeeder, q: np.ndarray) -> dict:
    """Return binding/broken constraints for joint injection q.

    Keys:
      thermal_overload_MW : max(|P_e| - K_e, 0) summed over edges (>0 => overload)
      worst_thermal_edge  : edge id with the largest thermal exceedance
      v_high, v_low       : max over/under voltage excursion (pu, not squared)
      any                 : bool, any constraint violated
      P_edge, v           : arrays for plotting
    """
    P_edge, R_edge = branch_flows(feeder, q)
    v_sq = voltages(feeder, P_edge, R_edge)
    K = thermal_limits(feeder, R_edge)

    exceed = np.maximum(np.abs(P_edge) - K, 0.0)
    exceed[0] = max(np.abs(P_edge[0]) - feeder.Srate[0], 0.0)  # substation xfmr
    worst_edge = int(np.argmax(exceed))
    thermal_over = float(exceed.sum())

    v = np.sqrt(np.clip(v_sq, 0.0, None))
    v_high = float(max(v.max() - feeder.vmax, 0.0))
    v_low = float(max(feeder.vmin - v.min(), 0.0))

    any_v = (v_high > 0) or (v_low > 0)
    any_thermal = thermal_over > 1e-9
    return {
        "thermal_overload_MW": thermal_over,
        "worst_thermal_edge": worst_edge,
        "thermal_margin_MW": float((K - np.abs(P_edge))[1:].min()),
        "v_high": v_high,
        "v_low": v_low,
        "v_min": float(v.min()),
        "v_max": float(v.max()),
        "any_thermal": bool(any_thermal),
        "any_voltage": bool(any_v),
        "any": bool(any_thermal or any_v),
        "P_edge": P_edge,
        "v": v,
    }


def inject_at(feeder: RadialFeeder, node: int, mw: float) -> np.ndarray:
    """Convenience: injection vector with `mw` at `node` (+discharge/-charge)."""
    q = np.zeros(feeder.N)
    q[node] = mw
    return q


if __name__ == "__main__":
    from data.topology import representative_feeder
    f = representative_feeder()
    base = violations(f, np.zeros(f.N))
    print(f"baseline: v in [{base['v_min']:.3f}, {base['v_max']:.3f}] pu, "
          f"thermal_overload={base['thermal_overload_MW']:.3f} MW")
    for mw in (0.5, 1.0, 2.0, 3.0, 4.0, 5.0):
        v = violations(f, inject_at(f, f.coloc_node, mw))
        print(f"discharge {mw:4.1f} MW @coloc: over={v['thermal_overload_MW']:.3f} MW "
              f"v_max={v['v_max']:.3f} any={v['any']}")
