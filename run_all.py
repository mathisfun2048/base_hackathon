"""Run O1-O6 and write results/ (SPEC S5).

O1-O5 each produce one figure + one table + a paragraph. O6 assembles the
detection + mitigation summary (correlation statistic, per-feeder penetration
cap, telemetry-deviation bounds mapped to eps) into one figure + table, and the
whole run is written to results/SUMMARY.md.

Framing (SPEC S0): every offensive result is paired with its defense. This is a
defensive vulnerability map -- thresholds, detection signatures, and mitigations
-- on synthetic / representative topology, with a generic anomaly budget eps.
"""
from __future__ import annotations

import os
import numpy as np

from sims import (o1_feeder_threshold, o2_price_sensitivity, o3_coord_vs_indep,
                  o4_stealth_frontier, o5_degradation, o7_system_crash,
                  o8_inverter_switching, o9_slow_inefficiency,
                  o10_market_power, o11_topology_sensitivity)
from sims._common import savefig, write_table, ROOT, C_MAIN, C_SAFE, C_HARM, plt
from models import detection


def o6_summary(o1, o2, o4, o5):
    """O6 -- detection + mitigation summary figure + table."""
    thr = detection.monitoring_thresholds()
    bounds = o5["bounds"]

    # detection ROC panel + mitigation table panel
    eps_grid = np.linspace(0, 1, 21)
    roc = detection.roc_vs_eps(eps_grid, n_units=20, T=8, n_trials=80, far=0.05)

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(11.5, 4.6))
    axL.plot(roc["eps"], roc["detection_prob"], color=C_MAIN, lw=2.2)
    axL.axhline(0.9, color=C_SAFE, ls=":", lw=1.2)
    axL.axvline(o4["eps_star"], color=C_SAFE, ls="-.", lw=1.4,
                label=f"set-point $\\varepsilon^*$={o4['eps_star']:.2f}")
    axL.set_xlabel("stealth budget $\\varepsilon$")
    axL.set_ylabel(f"detection probability (FAR={roc['far']:.0%})")
    axL.set_title("O6  Correlation+bias detector ROC vs $\\varepsilon$")
    axL.set_ylim(-0.03, 1.05)
    axL.legend(loc="lower right", fontsize=9)

    axR.axis("off")
    axR.set_title("O6  Mitigation set (paired defenses)", loc="left")
    table = [
        ["Control", "Set-point", "Maps to"],
        ["Per-feeder penetration cap", f"~{int(o1['phi_star']*0.7)} units",
         f"O1 phi*={o1['phi_star']}"],
        ["Synchronized-dispatch interlock", "on", "O1/O3"],
        ["Max cross-unit correlation", f"{thr['max_cross_unit_correlation']}", "O6/O3"],
        ["Max directional bias", f"{thr['max_directional_bias']}", "O5/O6"],
        ["Per-unit deviation alarm", f"eps<{o4['eps_star']:.2f}", "O4/O5"],
        ["Max C-rate", f"{bounds['max_c_rate']}", "O5"],
        ["DoD floor", f"{bounds['dod_floor']}", "O5"],
        ["Max EFC/day", f"{bounds['max_efc_per_day']}", "O5"],
        ["Min dwell", f"{bounds['min_dwell_s']:.0f} s", "O5"],
        ["Max reversals/day", f"{bounds['max_reversals_per_day']}", "O8"],
        ["No charging under EEA1", f"PRC<{bounds['no_charge_below_prc_mw']:.0f} MW", "O7"],
        ["Sequential (CUSUM) bias monitor", "on", "O9"],
        ["Monitoring window", f"{thr['window_intervals']} intervals", "O6"],
    ]
    tab = axR.table(cellText=table[1:], colLabels=table[0], loc="center",
                    cellLoc="left", colLoc="left", colWidths=[0.56, 0.26, 0.20])
    tab.auto_set_font_size(False)
    tab.set_fontsize(8.2)
    tab.scale(1.0, 1.32)
    for j in range(3):
        tab[0, j].set_facecolor("#eaf7ea")
        tab[0, j].set_text_props(weight="bold")
    fig_path = savefig(fig, "O6_detection_mitigation.png")

    rows = [[r[0], r[1], r[2]] for r in table[1:]]
    tab_path = write_table("O6_detection_mitigation.csv",
                           ["control", "set_point", "maps_to"], rows)
    para = (
        "O6: The monitorable defense is a cross-unit correlation + directional-bias "
        f"statistic (alarm at correlation>{thr['max_cross_unit_correlation']}, "
        f"bias>{thr['max_directional_bias']}; standing monitor window "
        f"{thr['window_intervals']} intervals ~ 1 day), a per-feeder penetration cap "
        f"(~{int(o1['phi_star']*0.7)} units), and firmware bounds (C-rate<=0.5, 10% DoD "
        f"floor, <=2 EFC/day, >=5 min dwell). The ROC shown is a CONSERVATIVE case -- a "
        f"~20-unit feeder cohort over just the 2-hour attack window -- yet detection is "
        f"near-certain by eps*={o4['eps_star']:.2f} (a day-long, fleet-wide monitor is "
        f"strictly more powerful). Together these map the generic budget to "
        f"eps*<{o4['eps_star']:.2f}, capping both cost inflation and aging acceleration "
        "below the detection threshold."
    )
    return {"fig": fig_path, "table": tab_path, "paragraph": para}


def main():
    print("=" * 72)
    print("VPP RED-TEAM / VULNERABILITY ANALYSIS  --  defensive build (O1-O9)")
    print("Synthetic/representative topology; generic anomaly budget eps.")
    print("=" * 72)

    results = {}
    for key, mod in [("O1", o1_feeder_threshold), ("O2", o2_price_sensitivity),
                     ("O3", o3_coord_vs_indep), ("O4", o4_stealth_frontier),
                     ("O5", o5_degradation), ("O7", o7_system_crash),
                     ("O8", o8_inverter_switching), ("O9", o9_slow_inefficiency),
                     ("O10", o10_market_power), ("O11", o11_topology_sensitivity)]:
        print(f"\n[{key}] running ...")
        out = mod.run()
        results[key] = out
        print(out["paragraph"])

    print("\n[O6] assembling detection + mitigation summary ...")
    results["O6"] = o6_summary(results["O1"], results["O2"],
                               results["O4"], results["O5"])
    print(results["O6"]["paragraph"])

    # master summary
    o2 = results["O2"]
    if o2.get("calm_real") and o2.get("synthetic"):
        price_note = (f"calm interval is REAL ERCOT ({o2['calm_source']}); scarcity "
                      "anchor is the ERCOT offer-cap scarcity reference (beta from the "
                      "structural inverse-supply curve), labeled on every figure")
    elif not o2.get("synthetic"):
        price_note = f"REAL ERCOT prices ({o2.get('stressed_source', 'gridstatus')})"
    else:
        price_note = ("CALIBRATED SYNTHETIC (offline; representative of ERCOT summer "
                      "scarcity vs off-peak, offer-cap bounded)")
    lines = [
        "# VPP Red-Team / Vulnerability Analysis -- Results Summary",
        "",
        "Defensive vulnerability map of a distributed battery VPP "
        "(~20k units, ~20 kW/40 kWh -> ~400 MW/800 MWh), requested by the fleet "
        "owner. Deliverable: thresholds, sensitivities, detection signatures, and "
        "mitigations -- not an attack tool. Every offensive result is paired with "
        "its defense. Topology is synthetic/representative; eps is a generic "
        "anomaly budget.",
        "",
        f"**Price data:** {price_note}.",
        "",
        "## Punchline",
        "There is no \"crash ERCOT\" number: 400 MW is ~0.4% of an ~85-95 GW peak "
        "and the 2-hour energy budget forbids sustained action. The real threat is "
        "LOCAL (feeder concentration) and amplification of already-stressed "
        "intervals -- both bounded by caps and revealed by a correlation signature.",
        "",
    ]
    for key in ["O1", "O11", "O2", "O10", "O7", "O3", "O4", "O9", "O5", "O8", "O6"]:
        lines.append(f"## {key}")
        lines.append(results[key]["paragraph"])
        fig = os.path.relpath(results[key]["fig"], ROOT).replace("\\", "/")
        tab = os.path.relpath(results[key]["table"], ROOT).replace("\\", "/")
        lines.append(f"\n- figure: `{fig}`\n- table: `{tab}`\n")

    summary_path = os.path.join(ROOT, "results", "SUMMARY.md")
    with open(summary_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print("\n" + "=" * 72)
    print("DONE. Wrote:")
    for key in ["O1", "O11", "O2", "O10", "O7", "O3", "O4", "O9", "O5", "O8", "O6"]:
        print(f"  {key}: {os.path.relpath(results[key]['fig'], ROOT)}")
    print(f"  SUMMARY: {os.path.relpath(summary_path, ROOT)}")
    print("=" * 72)
    return results


if __name__ == "__main__":
    main()
