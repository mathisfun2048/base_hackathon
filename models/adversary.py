"""Red-team objective functions on the SAME two graphs (SPEC S4).

DEFENSIVE USE ONLY. These objectives are the mathematical apparatus used to
LOCATE thresholds, stealth frontiers, and detection set-points -- the knee of
harm(eps) is the mitigation set-point (O4), the phi at which the correlation
premium departs from 1 is the penetration cap (O3). They are evaluated on
synthetic/representative graphs with a GENERIC stealth budget eps. They do NOT
produce, and this module deliberately does not expose, an optimized attack
schedule against any real fleet, firmware, or detector (SPEC S7 non-goals).

Objectives (paper notation, research.tex S3):
  J_cost   : system payment / cost inflation   sum_t dt*w_t*p_t(Q_t)*(L_t - Q_t)
  J_stress : overt feeder stress               sum of thermal/voltage violation
  J_degrade: fleet aging rate                  models.degradation.aging_rate
Stealth constraint (generic anomaly bound):
  || q_it - q_it^benign || <= eps   per interval / node.
"""
from __future__ import annotations

import numpy as np

from models import feasibility, degradation


# ----------------------------------------------------------------------------
# Objective 1: system payment / cost inflation
# ----------------------------------------------------------------------------
def payment(Q, L, price_fn, w=None, dt: float = 0.25) -> float:
    """Total load payment sum_t dt*w_t*p_t(Q_t)*(L_t - Q_t) ($)."""
    Q = np.atleast_1d(np.asarray(Q, dtype=float))
    L = np.atleast_1d(np.asarray(L, dtype=float))
    w = np.ones_like(Q) if w is None else np.asarray(w, dtype=float)
    p = price_fn(Q)
    return float(np.sum(dt * w * p * (L - Q)))


def J_cost(Q, L, price_fn, Q_benign=None, w=None, dt: float = 0.25) -> float:
    """Cost INFLATION (harm) relative to a benign reference dispatch.

    Positive = the deviation raised what load pays. This is the quantity O4 caps
    and O2/O3 compare; the adversary would maximize it, the defender bounds it.
    """
    if Q_benign is None:
        Q_benign = np.zeros_like(np.atleast_1d(Q))
    return payment(Q, L, price_fn, w, dt) - payment(Q_benign, L, price_fn, w, dt)


# ----------------------------------------------------------------------------
# Objective 2: overt feeder stress
# ----------------------------------------------------------------------------
def J_stress(feeder, q) -> float:
    """Sum of thermal-overload + voltage-excursion magnitude on the feeder."""
    v = feasibility.violations(feeder, q)
    return float(v["thermal_overload_MW"] + 10.0 * (v["v_high"] + v["v_low"]))


# ----------------------------------------------------------------------------
# Objective 3: fleet aging rate
# ----------------------------------------------------------------------------
def J_degrade(power_kw, temp_c: float = 25.0) -> float:
    """Effective per-day aging (fraction of life/day) for a unit schedule."""
    return float(degradation.aging_rate(power_kw, temp_c=temp_c)["damage_per_day"])


# ----------------------------------------------------------------------------
# Stealth budget
# ----------------------------------------------------------------------------
def stealth_ok(q, q_benign, eps) -> bool:
    """Per-interval / per-node detectability budget check (L-inf)."""
    return bool(np.max(np.abs(np.asarray(q) - np.asarray(q_benign))) <= eps + 1e-12)


def max_cost_harm_within_eps(L, price_fn, Q_benign, eps_mw, dt: float = 0.25,
                             direction: str = "inflate") -> dict:
    """Largest cost inflation achievable by an eps-bounded aggregate deviation.

    For a monotone price impact, the harm-maximizing deviation within the
    L-inf budget eps (MW, aggregate) is the CORNER: push net load in the
    cost-increasing direction by eps every interval. Returns the harm and the
    resulting aggregate dispatch -- a monotone frontier point, not a schedule
    to run. `direction='inflate'` reduces injection (raises L, raises price).
    """
    Q_benign = np.atleast_1d(np.asarray(Q_benign, dtype=float))
    L = np.atleast_1d(np.asarray(L, dtype=float))
    sgn = -1.0 if direction == "inflate" else +1.0   # inflate => reduce Q
    Q_adv = Q_benign + sgn * eps_mw
    harm = J_cost(Q_adv, L, price_fn, Q_benign=Q_benign, dt=dt)
    return {"eps_mw": float(eps_mw), "harm": harm, "Q_adv": Q_adv}


if __name__ == "__main__":
    from models.price import calibrate_to_observed
    cal = calibrate_to_observed(2000.0)          # a stressed anchor
    L = np.full(8, cal["L_obs"])
    Qb = np.zeros(8)
    for eps in (0, 50, 100, 200, 400):
        r = max_cost_harm_within_eps(L, cal["price"], Qb, eps)
        print(f"eps={eps:4d} MW  cost inflation = ${r['harm']:,.0f}")
