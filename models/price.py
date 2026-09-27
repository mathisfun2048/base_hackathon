"""Inverse-supply price model and LOCAL price sensitivity (SPEC S4, O2).

Reduced-form market-impact model, matching the paper's notation (research.tex
S3.4-3.5):

    p_t(Q_t) = f_t(L_t - Q_t)                                        (eq:price)

where L_t is exogenous net system load (MW) and Q_t is the fleet's aggregate
injection (MW, + = discharge/inject, so it REDUCES net load). f is the inverse
supply (merit-order) curve: an affine base plus a convex scarcity adder,
truncated at the system-wide offer cap.

The LOCAL price sensitivity is

    dp/dQ = -f'(L - Q)     =>   |dP/dQ| = f'(L)   at Q = 0.

This is the single number O2 is about. Per the paper (S "ERCOT anchoring and
identification limits"), the impact slope beta_t is a SCENARIO ASSUMPTION, not
a causally identified quantity: historical price/load correlation alone does
not identify beta_t. We therefore (a) calibrate the structural curve to a real
(or clearly-labeled synthetic) observed operating point p_obs at L_obs, and
(b) report beta_t = f'(L_obs) as a scenario slope to be swept, including zero.

Defensive purpose: O2 uses this to establish that the ~400 MW fleet has
near-zero leverage in calm hours and only marginal, offer-cap-bounded,
energy-limited leverage in scarcity -- i.e. there is NO "crash ERCOT" number.

Market vintage note (research.tex): ERCOT moved to Real-Time Co-optimization
Plus Batteries (RTC+B) on 2025-12-05; the legacy ORDC adder was replaced by
ancillary-service demand curves (ASDC) at that transition. The convex scarcity
adder below is an ORDC/ASDC-STYLE reduced form, not the live clearing engine;
tie any legacy-ORDC reading to its correct historical period.
"""
from __future__ import annotations

import numpy as np

# ERCOT system-wide offer cap ($/MWh). Public market parameter (High System-Wide
# Offer Cap, HCAP). Used only as a truncation on the reduced-form curve.
OFFER_CAP = 5000.0

# Representative ERCOT peak capacity (MW). Public, order-of-magnitude only;
# used for the "fleet MW as a fraction of the system" statement in O2.
SYSTEM_PEAK_MW = 90_000.0


def inverse_supply(
    L,
    *,
    base: float = 12.0,
    slope: float = 2.5e-4,
    Kcap: float = 85_000.0,
    knee: float = 0.86,
    cap: float = OFFER_CAP,
):
    """Inverse supply f(L): $/MWh as a function of net system load L (MW).

    merit-order (affine) + convex scarcity adder past a load `knee`, truncated
    at the offer cap. Continuous and nondecreasing on [0, Kcap), matching the
    monotonicity the paper requires of f_t.

    Parameters
    ----------
    base, slope : affine merit-order intercept ($/MWh) and slope ($/MWh / MW).
    Kcap        : effective supply capacity (MW) -- adder blows up as L -> Kcap.
    knee        : fraction of Kcap at which the convex scarcity adder switches on.
    cap         : offer-cap truncation ($/MWh).
    """
    L = np.asarray(L, dtype=float)
    L = np.clip(L, 0.0, Kcap - 1e-6)
    merit = base + slope * L
    frac = L / Kcap
    # cubic convex adder: 0 below the knee, rising steeply toward the cap.
    adder = np.where(frac > knee, ((frac - knee) / (1.0 - knee)) ** 3, 0.0)
    return np.minimum(merit + adder * (cap - merit), cap)


def fprime(L, *, h: float = 1.0, **kw):
    """Local price sensitivity f'(L) = dP/dL ($/MWh per MW), central difference.

    |dP/dQ| = f'(L) because Q enters as (L - Q). Returned value is >= 0.
    """
    L = np.asarray(L, dtype=float)
    return (inverse_supply(L + h, **kw) - inverse_supply(L - h, **kw)) / (2.0 * h)


def load_for_price(p_obs, *, Lo: float = 1.0, Hi: float = 84_999.0, **kw) -> float:
    """Invert f: find L such that inverse_supply(L) == p_obs (bisection).

    Used to turn an observed settlement price into an implied net load so the
    structural curve can be anchored at the real operating point.
    """
    p_obs = float(p_obs)
    lo, hi = float(Lo), float(Hi)
    flo, fhi = inverse_supply(lo, **kw), inverse_supply(hi, **kw)
    if p_obs <= flo:
        return lo
    if p_obs >= fhi:
        return hi
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if inverse_supply(mid, **kw) < p_obs:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def calibrate_to_observed(p_obs: float, L_obs: float | None = None, **kw):
    """Anchor the curve at a real (or labeled-synthetic) operating point.

    Returns a dict with:
      L_obs     : implied net load (given, or inverted from p_obs)
      beta      : local slope f'(L_obs) = |dP/dQ| scenario sensitivity
      shift     : additive shift making f_shifted(L_obs) == p_obs exactly
      price     : callable Q -> anchored counterfactual price (research.tex
                  eq:historicalanchor):  p(Q) = p_obs - beta*(Q - Q_ref)

    The anchored linear counterfactual is the paper's transparent specification;
    Q_ref = 0 treats the fleet as an incremental hypothetical fleet.
    """
    if L_obs is None:
        L_obs = load_for_price(p_obs, **kw)
    beta = float(fprime(L_obs, **kw))
    shift = float(p_obs - inverse_supply(L_obs, **kw))

    def price(Q, Q_ref: float = 0.0, beta_override: float | None = None):
        b = beta if beta_override is None else beta_override
        return p_obs - b * (np.asarray(Q, dtype=float) - Q_ref)

    return {
        "p_obs": float(p_obs),
        "L_obs": float(L_obs),
        "beta": beta,
        "shift": shift,
        "price": price,
        "curve_kwargs": kw,
    }


def structural_price(Q, L, **kw):
    """p_t(Q) = f(L - Q): fleet injection Q against structural inverse supply."""
    return inverse_supply(np.asarray(L, dtype=float) - np.asarray(Q, dtype=float), **kw)


if __name__ == "__main__":
    # Quick self-check / sanity print.
    for L in (40_000, 70_000, 78_000, 82_000, 84_000):
        print(f"L={L:>7} MW  p=f(L)={float(inverse_supply(L)):8.2f} $/MWh"
              f"  f'(L)={float(fprime(L)):.4e} ($/MWh)/MW")
