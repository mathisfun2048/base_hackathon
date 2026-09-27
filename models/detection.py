"""Benign-vs-adversarial detection (SPEC S4, O6) -- the monitorable defense.

Core idea (mirror of the paper's separability / coordination result): a benign
fleet DIVERSIFIES. Under exogenous prices and a product feasible set, each unit
optimizes locally, so cross-unit dispatch is decorrelated and unbiased relative
to the price-optimal action. A compromised fleet driven by one controller shows
(1) PERSISTENT CROSS-UNIT CORRELATION and (2) a DIRECTIONAL BIAS against the
price-optimal policy (charging into scarcity / discharging early). Either is a
telemetry statistic an operator can monitor without knowing the attacker.

We return the statistics and a ROC vs the stealth budget eps. eps is a GENERIC
anomaly bound (SPEC S0), not tuned to any real detector.
"""
from __future__ import annotations

import numpy as np


def correlation_statistic(dispatch_matrix) -> float:
    """Mean pairwise Pearson correlation of unit dispatch (units x time).

    ~0 for a diversified benign fleet; -> 1 for a synchronized compromised one.
    """
    X = np.asarray(dispatch_matrix, dtype=float)
    if X.ndim != 2 or X.shape[0] < 2:
        return 0.0
    Xc = X - X.mean(axis=1, keepdims=True)
    sd = np.sqrt((Xc ** 2).sum(axis=1))
    ok = sd > 1e-9
    if ok.sum() < 2:
        return 0.0
    Xn = Xc[ok] / sd[ok, None]
    C = Xn @ Xn.T
    n = C.shape[0]
    off = (C.sum() - np.trace(C)) / (n * (n - 1))
    return float(off)


def directional_bias(dispatch, price_optimal_sign) -> float:
    """Signed alignment of dispatch AGAINST the price-optimal action, in [-1,1].

    price_optimal_sign[t] = +1 if discharging is price-optimal at t (high price),
    -1 if charging is. Positive return => fleet is acting adversarially
    (e.g. charging into scarcity), the O5/O3 directional signature.
    """
    d = np.asarray(dispatch, dtype=float)
    s = np.asarray(price_optimal_sign, dtype=float)
    denom = np.sum(np.abs(d)) + 1e-9
    return float(-np.sum(d * s) / denom)


def _simulate_fleet(n_units, T, eps, adversarial, price_optimal_sign, rng):
    """Generate a dispatch matrix (units x T).

    benign: a DIVERSIFIED fleet -- each unit optimizes locally against its own
            state/forecast, so dispatch is idiosyncratic and cross-unit
            decorrelated (the separability premise).
    adversarial: a shared eps-bounded wrong-way bias pushes every unit the same
            way on top of the idiosyncratic behavior -> correlated + biased.
    The shared component's weight grows with eps, so both the correlation and
    the directional-bias statistics ramp smoothly with the stealth budget.
    """
    # idiosyncratic benign behavior (decorrelated across units)
    X = rng.normal(0.0, 1.0, size=(n_units, T))
    if adversarial:
        common = -price_optimal_sign[None, :] * eps      # shared wrong-way bias
        X = X + common
    return X


def roc_vs_eps(eps_grid, n_units: int = 200, T: int = 96, n_trials: int = 40,
               far: float = 0.05, seed: int = 0):
    """Detection power of the correlation+bias statistic as eps grows.

    For each eps: simulate many benign and adversarial fleets, form a combined
    statistic, set the threshold at the given benign false-alarm rate (far), and
    report the detection probability (true-positive rate). Returns arrays for
    plotting harm-vs-detectability and locating the mitigation set-point.
    """
    rng = np.random.default_rng(seed)
    price_sign = np.sign(np.sin(np.linspace(0, 2 * np.pi, T)))
    price_sign[price_sign == 0] = 1.0

    eps_grid = np.asarray(eps_grid, dtype=float)
    det_prob = np.zeros_like(eps_grid)
    corr_adv = np.zeros_like(eps_grid)
    bias_adv = np.zeros_like(eps_grid)

    for j, eps in enumerate(eps_grid):
        s_benign, s_adv = [], []
        for _ in range(n_trials):
            Xb = _simulate_fleet(n_units, T, eps, False, price_sign, rng)
            Xa = _simulate_fleet(n_units, T, eps, True, price_sign, rng)
            # combined statistic: correlation + directional bias of the mean
            sb = correlation_statistic(Xb) + max(directional_bias(Xb.mean(0), price_sign), 0)
            sa = correlation_statistic(Xa) + max(directional_bias(Xa.mean(0), price_sign), 0)
            s_benign.append(sb)
            s_adv.append(sa)
        s_benign = np.array(s_benign)
        s_adv = np.array(s_adv)
        thr = np.quantile(s_benign, 1.0 - far)      # threshold at target FAR
        det_prob[j] = float(np.mean(s_adv > thr))
        corr_adv[j] = float(np.mean([correlation_statistic(
            _simulate_fleet(n_units, T, eps, True, price_sign, rng)) for _ in range(5)]))
        bias_adv[j] = eps
    return {
        "eps": eps_grid,
        "detection_prob": det_prob,
        "corr_adversarial": corr_adv,
        "far": far,
    }


def monitoring_thresholds() -> dict:
    """Recommended monitorable set-points (O6 mitigation summary)."""
    return {
        "max_cross_unit_correlation": 0.2,   # alarm if fleet corr exceeds this
        "max_directional_bias": 0.1,         # alarm on persistent wrong-way bias
        "window_intervals": 96,              # ~1 day of 15-min data
    }


if __name__ == "__main__":
    out = roc_vs_eps(np.linspace(0, 1.0, 6))
    for e, d in zip(out["eps"], out["detection_prob"]):
        print(f"eps={e:.2f}  detection P(TPR@FAR=5%)={d:.2f}")
    print("thresholds:", monitoring_thresholds())
