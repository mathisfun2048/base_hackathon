"""Battery aging model -- sensitivity + detection signature + protective bounds.

SPEC S4 (O5) and S0/S7 guardrails. This module is DEFENSIVE. It quantifies:
  (a) how much a compromised controller could ACCELERATE fleet aging within a
      detectability budget,
  (b) the telemetry SIGNATURE that reveals such manipulation, and
  (c) the firmware/operational BOUNDS that cap it.
It does NOT emit an optimized schedule to maximize irreversible hardware damage
to any real fleet (SPEC S7 non-goal).

Public physics only:
  * DoD-dependent cycle life, Wohler/Woehler form  N(DoD) = a * DoD^(-b)
    (standard LFP shape; cf. NREL BLAST and published LFP cycle-life curves).
  * Equivalent full cycles via rainflow counting (ASTM E1049-style).
  * Miner's-rule linear damage accumulation.
  * Multiplicative C-rate and temperature (Arrhenius) acceleration factors.
All coefficients are generic literature-style values, tunable and labeled.
"""
from __future__ import annotations

import numpy as np

# --- unit + reference parameters (generic residential LFP) ---
UNIT_KWH = 40.0        # usable energy (kWh)
UNIT_KW = 20.0         # power rating (kW)  -> max ~0.5C
C_REF = 0.5            # reference C-rate for the multiplier
DOD_REF = 0.80         # reference DoD for a "nominal" cycle
T_REF_K = 298.15       # 25 C reference
EA_OVER_R = 4000.0     # Arrhenius Ea/R (K), literature-scale for Li-ion aging


def cycles_to_failure(dod, a: float = 4.0e3, b: float = 1.7) -> np.ndarray:
    """Cycle life vs depth-of-discharge (fraction in (0,1]). Wohler-type.

    Deeper cycles wear faster: N falls as DoD^(-b). a ~ 4e3 gives ~6000 cycles
    at 80% DoD (typical LFP: a*0.8^-1.7 ~ 5960)."""
    dod = np.clip(np.asarray(dod, dtype=float), 1e-3, 1.0)
    return a * dod ** (-b)


def rainflow_cycles(series):
    """ASTM E1049 rainflow counting of an SoC (or any) series.

    Returns list of (rng, mean, count) where count is 0.5 (half cycle) or 1.0.
    `rng` is the peak-to-peak amplitude of the counted cycle.
    """
    x = np.asarray(series, dtype=float)
    # reduce to turning points (reversals)
    if len(x) < 2:
        return []
    d = np.diff(x)
    tp = [x[0]]
    for i in range(1, len(d)):
        if d[i - 1] * d[i] < 0:      # sign change => turning point
            tp.append(x[i])
    tp.append(x[-1])

    cycles = []
    stack = []
    for p in tp:
        stack.append(p)
        while len(stack) >= 3:
            a, b, c = stack[-3], stack[-2], stack[-1]
            rng_ab = abs(b - a)
            rng_bc = abs(c - b)
            if rng_bc >= rng_ab:      # b-a is a closed full cycle
                cycles.append((rng_ab, (a + b) / 2.0, 1.0))
                del stack[-3:-1]      # remove a,b; keep c
            else:
                break
    # residuals: half cycles
    for i in range(len(stack) - 1):
        rng = abs(stack[i + 1] - stack[i])
        cycles.append((rng, (stack[i] + stack[i + 1]) / 2.0, 0.5))
    return cycles


def equivalent_full_cycles(soc_series) -> float:
    """Equivalent full cycles (EFC): count-weighted sum of cycle depths."""
    return float(sum(rng * cnt for rng, _, cnt in rainflow_cycles(soc_series)))


def c_rate_multiplier(c_rate, p: float = 1.0) -> float:
    """Acceleration factor for operating above the reference C-rate."""
    return float(np.maximum(c_rate / C_REF, 1e-6) ** p)


def temperature_multiplier(temp_c) -> float:
    """Arrhenius acceleration relative to 25 C."""
    T = float(temp_c) + 273.15
    return float(np.exp(EA_OVER_R * (1.0 / T_REF_K - 1.0 / T)))


def soc_from_power(power_kw, e_kwh: float = UNIT_KWH, dt_h: float = 0.25,
                   soc0: float = 0.5):
    """Integrate a per-interval power schedule (kW, + = discharge) into SoC.

    Returns SoC fraction trajectory clipped to [0,1]. Sign convention: positive
    power discharges (SoC falls)."""
    power_kw = np.asarray(power_kw, dtype=float)
    soc = np.empty(len(power_kw) + 1)
    soc[0] = soc0
    for t, pk in enumerate(power_kw):
        soc[t + 1] = np.clip(soc[t] - pk * dt_h / e_kwh, 0.0, 1.0)
    return soc


def aging_rate(power_kw, *, temp_c: float = 25.0, e_kwh: float = UNIT_KWH,
               dt_h: float = 0.25, a: float = 4.0e3, b: float = 1.7) -> dict:
    """Fractional capacity-loss proxy for a dispatch schedule.

    Combines rainflow damage (Miner) with C-rate and temperature multipliers.
    Returns a dict with EFC, damage (fraction of life consumed over the horizon),
    per-day damage, and the acceleration multipliers -- all monitorable proxies,
    not a manufacturer warranty model.
    """
    power_kw = np.asarray(power_kw, dtype=float)
    soc = soc_from_power(power_kw, e_kwh=e_kwh, dt_h=dt_h)
    cyc = rainflow_cycles(soc)
    efc = float(sum(rng * cnt for rng, _, cnt in cyc))

    # Miner damage from depth-dependent life
    damage = float(sum(cnt / cycles_to_failure(rng, a=a, b=b) for rng, _, cnt in cyc if rng > 1e-6))

    c_rate = float(np.max(np.abs(power_kw)) / e_kwh) if len(power_kw) else 0.0
    k_c = c_rate_multiplier(c_rate)
    k_t = temperature_multiplier(temp_c)
    damage_eff = damage * k_c * k_t

    horizon_h = len(power_kw) * dt_h
    per_day = damage_eff * (24.0 / horizon_h) if horizon_h > 0 else 0.0
    return {
        "efc": efc,
        "damage": damage,
        "damage_eff": damage_eff,
        "damage_per_day": per_day,
        "c_rate": c_rate,
        "k_c_rate": k_c,
        "k_temp": k_t,
        "min_soc": float(soc.min()),
        "max_soc": float(soc.max()),
    }


def aging_from_soc(soc_series, *, dt_h: float = 0.25, e_kwh: float = UNIT_KWH,
                   temp_c: float = 25.0, a: float = 4.0e3, b: float = 1.7) -> dict:
    """Aging metrics computed directly from a SoC trajectory (fraction in [0,1]).

    Preferred entry point when a SoC path is available: the DoD/Wohler model is
    inherently a function of SoC excursions, and staying in SoC space avoids the
    power->SoC integration saturating at the [0,1] rails. C-rate is inferred from
    the per-interval SoC slope. Monotone in cycling amplitude by construction.
    """
    soc = np.asarray(soc_series, dtype=float)
    cyc = rainflow_cycles(soc)
    efc = float(sum(rng * cnt for rng, _, cnt in cyc))
    damage = float(sum(cnt / cycles_to_failure(rng, a=a, b=b)
                       for rng, _, cnt in cyc if rng > 1e-6))
    dsoc = np.abs(np.diff(soc)) if len(soc) > 1 else np.array([0.0])
    c_rate = float(dsoc.max() / dt_h)          # C-rate = (dSoC*E/dt)/E = dSoC/dt
    k_c = c_rate_multiplier(c_rate)
    k_t = temperature_multiplier(temp_c)
    damage_eff = damage * k_c * k_t
    horizon_h = (len(soc) - 1) * dt_h
    per_day = damage_eff * (24.0 / horizon_h) if horizon_h > 0 else 0.0
    return {"efc": efc, "damage": damage, "damage_eff": damage_eff,
            "efc_per_day": efc * (24.0 / horizon_h) if horizon_h > 0 else 0.0,
            "damage_per_day": per_day, "c_rate": c_rate, "k_c_rate": k_c,
            "k_temp": k_t, "min_soc": float(soc.min()), "max_soc": float(soc.max())}


def detection_signature(power_kw, benign_power_kw, *, price_optimal_sign=None,
                        temp_c: float = 25.0) -> dict:
    """Telemetry markers that reveal aging-accelerating manipulation (O5).

    Compares a candidate schedule to a benign reference and returns:
      efc_ratio        : equivalent-cycles/day vs benign (>1 => more wear)
      damage_ratio     : effective damage/day vs benign
      directional_bias : mean signed deviation aligned AGAINST the price-optimal
                         action (charging into scarcity / discharging early) --
                         normalized to [-1,1]; >0 is the adversarial direction
      dod_floor_breach : fraction of intervals below a 10% SoC floor
    These are single-unit markers; cross-unit correlation is added in
    models/detection.py (the fleet-level statistic).
    """
    power_kw = np.asarray(power_kw, dtype=float)
    benign_power_kw = np.asarray(benign_power_kw, dtype=float)
    ar = aging_rate(power_kw, temp_c=temp_c)
    ar_b = aging_rate(benign_power_kw, temp_c=temp_c)

    dev = power_kw - benign_power_kw
    if price_optimal_sign is not None:
        pos = np.asarray(price_optimal_sign, dtype=float)
        # adversarial deviation = component OPPOSITE the price-optimal sign
        denom = np.sum(np.abs(dev)) + 1e-9
        bias = float(-np.sum(dev * pos) / denom)
    else:
        bias = float(np.mean(np.sign(dev))) if len(dev) else 0.0

    soc = soc_from_power(power_kw)
    dod_floor_breach = float(np.mean(soc < 0.10))
    return {
        "efc_ratio": ar["efc"] / (ar_b["efc"] + 1e-9),
        "damage_ratio": ar["damage_eff"] / (ar_b["damage_eff"] + 1e-9),
        "directional_bias": bias,
        "dod_floor_breach": dod_floor_breach,
        "efc_per_day_candidate": ar["efc"] * (24.0 / (len(power_kw) * 0.25)),
        "efc_per_day_benign": ar_b["efc"] * (24.0 / (len(benign_power_kw) * 0.25)),
    }


def inverter_cycles_to_failure(delta_Tj, A: float = 1.024e14, n: float = 5.0) -> float:
    """Power-electronics (IGBT/solder) life vs junction-temperature swing.

    Coffin-Manson power-cycling form N_f = A * dT_j^(-n). Calibrated so a 40 C
    junction swing gives ~1e6 cycles and an 80 C swing ~3e4 (representative of
    published IGBT power-cycling curves). Each charge<->discharge reversal is ~one
    power cycle, so rapid inverter switching consumes this life directly.
    """
    return float(A * max(delta_Tj, 1.0) ** (-n))


def inverter_switching_wear(reversals_per_day, *, delta_Tj: float = 45.0,
                            micro_dod: float = 0.02, a: float = 4.0e3,
                            b: float = 1.7) -> dict:
    """Battery + inverter wear from a given charge/discharge REVERSAL rate.

    Models the "constant inverter switching" cyber-attack (SPEC user Q4): a
    compromised controller flips the inverter between charge and discharge far
    more often than any price-optimal policy would. Returns:
      inverter_life_per_day : fraction of inverter power-cycling life consumed/day
      inverter_life_years   : implied inverter lifetime at this rate
      battery_damage_per_day: fraction of battery cycle-life consumed/day (Miner)
      battery_efc_per_day   : equivalent full cycles/day from the micro-cycling
      battery_life_years    : implied battery lifetime at this rate
    Each reversal is ~one inverter power cycle; two reversals ~one battery
    micro-cycle of depth `micro_dod`.
    """
    r = float(reversals_per_day)
    Nf_inv = inverter_cycles_to_failure(delta_Tj)
    inv_per_day = r / Nf_inv
    micro_cycles = r / 2.0
    efc_per_day = micro_cycles * micro_dod
    batt_damage_day = micro_cycles / cycles_to_failure(micro_dod, a=a, b=b)
    return {
        "reversals_per_day": r,
        "inverter_life_per_day": inv_per_day,
        "inverter_life_years": (1.0 / inv_per_day / 365.0) if inv_per_day > 0 else float("inf"),
        "battery_damage_per_day": batt_damage_day,
        "battery_efc_per_day": efc_per_day,
        "battery_life_years": (1.0 / batt_damage_day / 365.0) if batt_damage_day > 0 else float("inf"),
    }


def protective_bounds(feeder=None) -> dict:
    """Firmware / operational caps that CAP the O5 vulnerability (mitigation).

    These are the defensive set-points paired with the degradation result:
      max_c_rate   : hard C-rate ceiling (keeps k_c_rate ~ 1)
      dod_floor    : minimum SoC (blocks deep-cycling attacks)
      max_efc_per_day : equivalent-full-cycle budget per day (rate limiter)
      min_dwell_s  : minimum dwell between charge/discharge reversals
      max_ramp_kw_s: ramp-rate limit
    """
    return {
        "max_c_rate": 0.5,          # = unit rating; no over-driving
        "dod_floor": 0.10,          # never below 10% SoC
        "max_efc_per_day": 2.0,     # ~2 equivalent full cycles/day ceiling
        "min_dwell_s": 300.0,       # >= 5 min between reversals
        "max_ramp_kw_s": UNIT_KW / 60.0,   # full swing no faster than ~1 min
        "max_reversals_per_day": 48,       # switching-count budget (anti inverter-abuse)
        "no_charge_below_prc_mw": 2300.0,  # forbid coordinated charging under EEA1
    }


if __name__ == "__main__":
    T = 96
    # benign: one gentle daily cycle
    benign = 8.0 * np.sin(np.linspace(0, 2 * np.pi, T))
    # candidate: extra reversals (more wear) but same peak power
    adv = benign + 4.0 * np.sin(np.linspace(0, 12 * np.pi, T))
    print("benign  :", {k: round(v, 4) for k, v in aging_rate(benign).items()})
    print("candidate:", {k: round(v, 4) for k, v in aging_rate(adv).items()})
    print("signature:", {k: round(v, 4) for k, v in
                         detection_signature(adv, benign).items()})
    print("bounds  :", protective_bounds())
