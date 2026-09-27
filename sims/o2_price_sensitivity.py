"""O2 -- Price sensitivity under stress vs calm (SPEC S2).

Estimate local dP/dQ = -f'(L) = beta on a genuinely stressed interval vs a calm
one, using ERCOT prices (real via gridstatus, else calibrated synthetic). Show
leverage ~ 0 in normal hours and only marginal under scarcity, and state
explicitly, backed by the number, that there is NO system crash from the fleet's
~400 MW.

DEFENSE paired with the result: no system-wide MW cap is warranted (leverage is
structural and tiny); the actionable controls are the LOCAL feeder cap (O1) and
the correlation/deviation detector (O6). Scarcity intervals are where even
marginal leverage concentrates, so monitoring focuses there.
"""
from __future__ import annotations

import numpy as np

from data.fetch_ercot import find_stressed_interval
from models.price import inverse_supply, fprime, load_for_price, SYSTEM_PEAK_MW
from sims._common import savefig, write_table, annotate_defense, C_HARM, C_MAIN, C_SAFE, C_MUTED, plt

FLEET_MW = 400.0
FLEET_MWH = 800.0


def run():
    stressed, calm = find_stressed_interval()
    synthetic = not stressed.real          # scarcity anchor is a reference/synthetic
    calm_real = calm.real

    # anchor each operating point: observed price -> implied net load -> slope
    L_stress = load_for_price(stressed.peak_price)
    L_calm = load_for_price(calm.peak_price)
    beta_stress = float(fprime(L_stress))     # ($/MWh)/MW
    beta_calm = float(fprime(L_calm))
    ratio = beta_stress / max(beta_calm, 1e-12)

    dp_stress = beta_stress * FLEET_MW        # max price move from full fleet
    dp_calm = beta_calm * FLEET_MW
    pct_stress = 100 * dp_stress / stressed.peak_price
    pct_calm = 100 * dp_calm / calm.peak_price
    fleet_frac_peak = 100 * FLEET_MW / SYSTEM_PEAK_MW
    sustain_h = FLEET_MWH / FLEET_MW

    # ---- figure: two panels ----
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(11.5, 4.4))

    # panel L: inverse supply with the two operating points + local slopes
    Lgrid = np.linspace(20_000, 84_900, 500)
    axL.plot(Lgrid, inverse_supply(Lgrid), color=C_MUTED, lw=2, label="inverse supply $f(L)$")
    for L, p, c, lab, beta in [
        (L_calm, calm.peak_price, C_MAIN, "calm", beta_calm),
        (L_stress, stressed.peak_price, C_HARM, "scarcity", beta_stress),
    ]:
        axL.scatter([L], [inverse_supply(L)], color=c, zorder=5)
        dL = 4000
        axL.plot([L - dL, L + dL],
                 [inverse_supply(L) - beta * dL, inverse_supply(L) + beta * dL],
                 color=c, lw=2.4,
                 label=f"{lab}: $|dP/dQ|$={beta:.2e} (\\$/MWh)/MW")
    axL.set_xlabel("net system load $L$ (MW)")
    axL.set_ylabel("price $f(L)$ ($/MWh)")
    axL.set_title("O2  Local price sensitivity: calm vs scarcity")
    axL.legend(loc="upper left", fontsize=8.5)

    # panel R: fleet price move (log) + fraction-of-system context
    axR.bar(["calm", "scarcity"], [dp_calm, dp_stress], color=[C_MAIN, C_HARM])
    axR.set_yscale("log")
    axR.set_ylabel("max price move from full 400 MW fleet ($/MWh)")
    axR.set_title("O2  Fleet leverage is tiny in calm, marginal in scarcity")
    for i, (v, pct) in enumerate([(dp_calm, pct_calm), (dp_stress, pct_stress)]):
        axR.text(i, v, f"  {v:.2g} $/MWh\n  ({pct:.2g}% of price)", va="bottom", fontsize=9)
    annotate_defense(axR, "no system MW cap needed; enforce LOCAL feeder cap (O1)\n"
                          "+ correlation/deviation detector (O6); watch scarcity")
    fig_path = savefig(fig, "O2_price_sensitivity.png")

    # ---- table ----
    rows = [
        ["calm data source", calm.source],
        ["stressed data source", stressed.source],
        ["settlement", f"{stressed.location_type}"],
        ["stressed price ($/MWh)", f"{stressed.peak_price:.1f}"],
        ["calm price ($/MWh)", f"{calm.peak_price:.1f}"],
        ["implied load stressed (MW)", f"{L_stress:.0f}"],
        ["implied load calm (MW)", f"{L_calm:.0f}"],
        ["beta scarcity ($/MWh per MW)", f"{beta_stress:.3e}"],
        ["beta calm ($/MWh per MW)", f"{beta_calm:.3e}"],
        ["scarcity/calm sensitivity ratio", f"{ratio:.0f}x"],
        ["fleet price move, scarcity ($/MWh)", f"{dp_stress:.1f} ({pct_stress:.2f}% of price)"],
        ["fleet price move, calm ($/MWh)", f"{dp_calm:.3f} ({pct_calm:.3f}% of price)"],
        ["fleet MW as % of ~90 GW peak", f"{fleet_frac_peak:.2f}%"],
        ["energy-limited sustain time (h)", f"{sustain_h:.1f}"],
    ]
    tab_path = write_table("O2_price_sensitivity.csv", ["quantity", "value"], rows)

    para = (
        f"O2: Local price sensitivity is ~{ratio:.0f}x larger in scarcity "
        f"(beta={beta_stress:.2e}) than in calm (beta={beta_calm:.2e}) "
        f"($/MWh per MW). Even at scarcity the full 400 MW fleet moves price by at most "
        f"~{dp_stress:.0f} $/MWh ({pct_stress:.1f}% of the ${stressed.peak_price:.0f} "
        f"level), and in calm hours by {dp_calm:.2f} $/MWh ({pct_calm:.2f}%). "
        f"NO SYSTEM CRASH: 400 MW is {fleet_frac_peak:.2f}% of a ~90 GW peak and the "
        f"800 MWh budget forbids sustained action beyond ~{sustain_h:.0f} h. Leverage "
        f"is structural, offer-cap bounded, and energy-limited; the real risk is LOCAL "
        f"(O1) and amplification of already-stressed intervals, not system collapse."
        + (f" [calm: REAL ERCOT {calm.date} Load Zone; scarcity: offer-cap reference]"
           if (calm_real and synthetic) else
           (" [prices: calibrated synthetic]" if synthetic else " [prices: real ERCOT]"))
    )
    return {"beta_stress": beta_stress, "beta_calm": beta_calm, "ratio": ratio,
            "dp_stress": dp_stress, "dp_calm": dp_calm,
            "fleet_frac_peak": fleet_frac_peak, "synthetic": synthetic,
            "calm_real": calm_real, "calm_date": calm.date,
            "calm_source": calm.source, "stressed_source": stressed.source,
            "fig": fig_path, "table": tab_path, "paragraph": para}


if __name__ == "__main__":
    out = run()
    print(out["paragraph"])
    print("figure:", out["fig"])
