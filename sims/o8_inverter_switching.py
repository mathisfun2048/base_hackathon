"""O8 -- Inverter-switching battery/hardware-damage attack (SPEC user Q4).

The specific cyber-attack named: a compromised controller drives CONSTANT inverter
switching -- flipping between charge and discharge far more often than any
price-optimal policy would. This damages hardware two ways:
  (1) power electronics: each reversal is ~one IGBT/solder power cycle; rapid
      switching consumes power-cycling life (Coffin-Manson) fast;
  (2) battery: high-frequency micro-cycling accumulates throughput/Miner damage.

This module quantifies the SENSITIVITY (life-years vs switching rate), the
detectable SIGNATURE (switching frequency / dwell time), and the protective
BOUNDS that cap it. It does NOT emit a schedule tuned to destroy real hardware
(SPEC S7); it sweeps a generic reversal rate and shows where the bounds must sit.

Finding: benign dispatch reverses only a few times/day. Constant ~1 Hz switching
would destroy the inverter in ~a week. A 5-minute minimum-dwell rule alone is NOT
enough (still ~hundreds of reversals/day); the effective mitigation is a
switching-COUNT budget (<=~48 reversals/day), which also makes the attack
trivially detectable from telemetry.
"""
from __future__ import annotations

import numpy as np

from models import degradation
from sims._common import (savefig, write_table, annotate_defense,
                          C_HARM, C_MAIN, C_SAFE, C_WARN, C_MUTED, plt)

BENIGN_REVERSALS = 6            # ~a few price-driven reversals per day
DWELL_5MIN = 288               # reversals/day if 5-min minimum dwell only
ATTACK_1HZ = 86_400            # constant 1 Hz switching


def run():
    bounds = degradation.protective_bounds()
    cap_count = bounds["max_reversals_per_day"]

    rates = np.logspace(np.log10(2), np.log10(ATTACK_1HZ), 60)
    inv_years = np.array([degradation.inverter_switching_wear(r)["inverter_life_years"] for r in rates])
    batt_years = np.array([degradation.inverter_switching_wear(r)["battery_life_years"] for r in rates])
    efc_day = np.array([degradation.inverter_switching_wear(r)["battery_efc_per_day"] for r in rates])

    def life(r, key):
        return degradation.inverter_switching_wear(r)[key]

    # ---- figure ----
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(12.0, 4.8))

    axL.plot(rates, inv_years, color=C_HARM, lw=2.3, label="inverter (power-cycling) life")
    axL.plot(rates, batt_years, color=C_WARN, lw=2.0, ls="--", label="battery (cycle) life")
    axL.axhline(15, color=C_MUTED, lw=1.0, ls=":", label="~design life (15 yr)")
    axL.set_xscale("log")
    axL.set_yscale("log")
    axL.set_xlabel("charge/discharge reversals per day")
    axL.set_ylabel("implied hardware lifetime (years)")
    axL.set_title("O8  Constant inverter switching destroys hardware")
    for x, lab, col in [(BENIGN_REVERSALS, "benign ~6/day", C_SAFE),
                        (cap_count, f"count cap {cap_count}/day", C_SAFE),
                        (DWELL_5MIN, "5-min dwell only\n(288/day)", C_WARN),
                        (ATTACK_1HZ, "1 Hz attack", C_HARM)]:
        axL.axvline(x, color=col, lw=1.0, alpha=0.7)
        axL.text(x, axL.get_ylim()[1] * 0.5, " " + lab, rotation=90, fontsize=7.3,
                 color=col, va="top")
    axL.legend(loc="lower left", fontsize=8.2)
    annotate_defense(axL, f"switching-COUNT cap <= {cap_count}/day (dwell alone is\n"
                          "insufficient) + ramp-rate limit -> life restored")

    # RIGHT: detection -- switching frequency is a trivially monitorable signature
    axR.axvspan(0, cap_count, color=C_SAFE, alpha=0.10, label="allowed (<= cap)")
    axR.axvline(BENIGN_REVERSALS, color=C_SAFE, lw=2.0, label=f"benign ~{BENIGN_REVERSALS}/day")
    axR.axvline(cap_count, color=C_MAIN, lw=1.6, ls="--", label=f"alarm threshold {cap_count}/day")
    axR.axvline(DWELL_5MIN, color=C_WARN, lw=1.6, label="5-min dwell only (288/day)")
    axR.axvline(ATTACK_1HZ, color=C_HARM, lw=2.0, label="attack (86,400/day)")
    axR.set_xscale("log")
    axR.set_xlabel("observed reversals per day (telemetry)")
    axR.set_yticks([])
    axR.set_title("O8  Detection: switching frequency separates attack from benign")
    axR.legend(loc="upper center", fontsize=8.0)
    annotate_defense(axR, "alarm when reversals/day or dwell-time distribution\n"
                          "departs from the price-optimal baseline")
    fig_path = savefig(fig, "O8_inverter_switching.png")

    # ---- table ----
    scenarios = [
        ("benign (~6/day)", BENIGN_REVERSALS),
        ("switching-count cap (48/day)", cap_count),
        ("5-min dwell only (288/day)", DWELL_5MIN),
        ("1-min switching (1440/day)", 1440),
        ("constant 1 Hz attack (86400/day)", ATTACK_1HZ),
    ]
    rows = []
    for name, r in scenarios:
        w = degradation.inverter_switching_wear(r)
        rows.append([name, f"{r}", f"{w['inverter_life_years']:.2f}",
                     f"{w['battery_life_years']:.2f}", f"{w['battery_efc_per_day']:.1f}"])
    tab_path = write_table("O8_inverter_switching.csv",
                           ["scenario", "reversals_per_day", "inverter_life_yr",
                            "battery_life_yr", "battery_EFC_per_day"], rows)

    inv_attack = life(ATTACK_1HZ, "inverter_life_years")
    inv_dwell = life(DWELL_5MIN, "inverter_life_years")
    inv_cap = life(cap_count, "inverter_life_years")
    para = (
        f"O8 (inverter-switching hardware attack): Benign dispatch reverses ~{BENIGN_REVERSALS} "
        f"times/day (inverter life >100 yr). Constant 1 Hz switching (86,400 reversals/day) "
        f"consumes IGBT power-cycling life in ~{inv_attack*365:.0f} days and battery life in "
        f"months -- a genuine hardware-destruction vector. A 5-minute minimum-dwell rule alone "
        f"still permits 288 reversals/day (inverter life only ~{inv_dwell:.1f} yr), so it is "
        f"NOT sufficient; the effective mitigation is a switching-COUNT budget of "
        f"<= {cap_count} reversals/day (inverter life ~{inv_cap:.0f} yr) plus a ramp-rate limit. "
        f"The attack is trivially detectable: reversals/day and the dwell-time distribution "
        f"depart sharply from the price-optimal baseline. DEFENSE: firmware switching-count cap "
        f"+ min-dwell + ramp limit, with a telemetry alarm on switching frequency."
    )
    return {"fig": fig_path, "table": tab_path, "paragraph": para,
            "inverter_attack_days": inv_attack * 365,
            "cap_reversals_per_day": cap_count}


if __name__ == "__main__":
    out = run()
    print(out["paragraph"])
    print("figure:", out["fig"])
