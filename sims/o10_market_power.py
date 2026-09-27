"""O10 -- Market-making at scale IS the harm, in plain dollars (discovery payoff).

Narrative lineage (the presentation's arc):
  research.tex : the three regimes differ ONLY by the price each internalizes.
                 The central / strategic fleet internalizes  p_t(Q) + Q*p'(Q),
                 i.e. it WITHHOLDS to avoid crashing its own price. That single
                 term is market power.
  cheat_sheet  : same two graphs, flipped objective; the owner's coordination
                 premium rho is, sign-for-sign, the adversary's cost-inflation
                 lever.
  O10 (here)   : put that lever in DOLLARS ON EVERYONE'S BILL, and sweep fleet
                 size 20k (today) -> 240k (2 yr at 3x/yr growth). The harm that is
                 ~0 today becomes systemic at scale. Private gain != social good.

Why the number is legible and large: in a single-clearing-price market EVERY MWh
settles at the marginal price. Moving the price a few $/MWh is therefore paid on
ALL of ERCOT's load -- a small percentage on an enormous base. That is why a
concentrated fleet exercising market power during scarcity is a wealth TRANSFER
from ratepayers, not value creation; with round-trip losses it is negative-sum
(cheat_sheet Remark on round-trip efficiency).

This is a systemic-risk quantification for the fleet owner / operator, computed on
the public/synthetic ERCOT price STRUCTURE (labeled). It is not a trading strategy.

DEFENSE (paired): the market-power lever is capped by the same controls as the
physical ones -- a per-scarcity-interval fleet-share screen, the cross-unit
correlation detector (O6), and a no-coordinated-withhold rule under scarcity/low
reserve (O7). The screen set-point is the fleet share at which cost inflation
first exceeds a materiality threshold (marked on the figure).
"""
from __future__ import annotations

import numpy as np

from data.fetch_ercot import find_stressed_interval
from models.price import inverse_supply, load_for_price, OFFER_CAP, SYSTEM_PEAK_MW
from sims._common import (savefig, write_table, annotate_defense,
                          C_HARM, C_MAIN, C_SAFE, C_WARN, C_MUTED, plt)

UNIT_KW = 20.0
UNIT_KWH = 40.0                 # 2-hour asset
WINDOW_H = 2.0                  # a 2-hour scarcity window (the reachable action)
# ERCOT context for the per-household translation (public, order-of-magnitude,
# clearly labeled -- NOT a precise settlement).
ERCOT_HOUSEHOLDS = 10_000_000
SCARCITY_EVENTS_PER_SUMMER = 5  # illustrative cadence for the annualized view

# Fleet growth: 20k today, 3x/year -> the 2-year horizon the owner flagged.
FLEET_TODAY = 20_000
GROWTH_PER_YEAR = 3.0
FLEET_2YR = int(FLEET_TODAY * GROWTH_PER_YEAR ** 2)   # 180k
# The owner's own figure was ~240k in 2 yr; use their number as the marked horizon.
FLEET_HORIZON = 240_000


def fleet_mw(n_units):
    return n_units * UNIT_KW / 1000.0


def cost_to_all_load(Q, L, window_h=WINDOW_H):
    """What ALL settled load pays at the single clearing price f(L-Q), over the
    window. Price is set at the margin but paid on the whole load L."""
    p = float(inverse_supply(L - Q))
    return p * L * window_h, p


def owner_profit(Q, L, window_h=WINDOW_H):
    """Fleet revenue = clearing price x energy it sells (Q>0 discharge sells;
    Q<0 charge buys = negative). The self-cannibalization term lives here."""
    p = float(inverse_supply(L - Q))
    return p * Q * window_h


def rational_withhold_mw(F, L, n_grid=400):
    """The profit-maximizing discharge Q in [0, F]: the strategic fleet holds
    energy back to keep price up (research.tex central-fleet marginal term)."""
    Qs = np.linspace(0.0, F, n_grid)
    prof = np.array([owner_profit(q, L) for q in Qs])
    return float(Qs[int(np.argmax(prof))])


def run():
    # ---- price anchor: a stressed (scarcity) interval, structure labeled ----
    stressed, calm = find_stressed_interval()
    p_scarcity = float(stressed.peak_price)         # ~$2,500 offer-cap reference
    L = load_for_price(p_scarcity)                  # implied net load (~82.5 GW)
    p_calm = float(calm.peak_price)
    L_calm = load_for_price(p_calm)

    # ---- sweep fleet size ----
    sizes = np.array([20, 40, 80, 120, 160, 200, 240, 300], dtype=float) * 1000
    F = fleet_mw(sizes)                              # MW at each fleet size

    cost_help, cost_rational, cost_hostile, p_hostile = [], [], [], []
    owner_gain, public_cost = [], []
    for f in F:
        # helpful honest market-maker: discharge everything into the peak
        c_help, _ = cost_to_all_load(+f, L)
        # rational owner: withhold to max its own profit
        q_rat = rational_withhold_mw(f, L)
        c_rat, _ = cost_to_all_load(+q_rat, L)
        # hostile / compromised: charge INTO scarcity (worst case)
        c_host, ph = cost_to_all_load(-f, L)
        cost_help.append(c_help); cost_rational.append(c_rat)
        cost_hostile.append(c_host); p_hostile.append(ph)
        # private vs public, exercising power vs the helpful baseline
        owner_gain.append(owner_profit(q_rat, L) - owner_profit(+f, L))
        public_cost.append(c_rat - c_help)
    cost_help = np.array(cost_help); cost_rational = np.array(cost_rational)
    cost_hostile = np.array(cost_hostile); p_hostile = np.array(p_hostile)
    owner_gain = np.array(owner_gain); public_cost = np.array(public_cost)

    # harm = extractive/hostile minus the socially-best (helpful) case
    harm_rational = cost_rational - cost_help
    harm_hostile = cost_hostile - cost_help

    # leverage ratio: public cost per $1 of private gain (the killer stat)
    idx_h = int(np.argmin(np.abs(sizes - FLEET_HORIZON)))
    lever = float(public_cost[idx_h] / max(owner_gain[idx_h], 1.0))

    # per-household translation at the horizon fleet
    per_hh_event = harm_hostile[idx_h] / ERCOT_HOUSEHOLDS
    per_hh_summer = per_hh_event * SCARCITY_EVENTS_PER_SUMMER

    # baseline: what load pays with NO fleet (price = f(L))
    base_cost = float(inverse_supply(L)) * L * WINDOW_H

    # ---- figure ----
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(12.2, 4.9))

    xk = sizes / 1000.0
    axL.axhline(base_cost / 1e6, color=C_MUTED, lw=1.3, ls=":",
                label="no fleet (status quo)")
    axL.plot(xk, cost_help / 1e6, color=C_SAFE, lw=2.2,
             label="helpful market-maker (discharges -> price DOWN)")
    axL.plot(xk, cost_rational / 1e6, color=C_WARN, lw=2.2,
             label="self-interested owner (withholds relief)")
    axL.plot(xk, cost_hostile / 1e6, color=C_HARM, lw=2.4,
             label="hostile / compromised (charges -> price UP)")
    axL.fill_between(xk, cost_help / 1e6, cost_hostile / 1e6,
                     color=C_HARM, alpha=0.06)
    y0, y1 = axL.get_ylim()
    for xu, lab, col, ha in [(FLEET_TODAY / 1000, "today 20k", C_MUTED, "left"),
                             (FLEET_HORIZON / 1000, "~2 yr 240k", C_MAIN, "right")]:
        axL.axvline(xu, color=col, lw=1.2, ls="--", alpha=0.8)
        axL.text(xu, y0 + 0.03 * (y1 - y0), " " + lab + " ", rotation=90,
                 fontsize=8, color=col, va="bottom", ha=ha)
    axL.set_xlabel("fleet size (thousands of units)  --  3x/yr growth")
    axL.set_ylabel(r"what ALL of Texas pays in ONE 2-hour window (\$M)")
    axL.set_title("O10  Market-making at scale IS the harm\n"
                  "every MWh settles at the one marginal price the fleet moves")
    axL.legend(loc="center left", fontsize=7.8)
    annotate_defense(axL, "per-scarcity fleet-share screen + no coordinated\n"
                          "withhold under low reserve (O7) + correlation detector (O6)")

    # RIGHT: private gain vs public cost at the horizon fleet (negative-sum)
    labels = ["fleet owner's\nprivate gain", "Texas ratepayers'\nextra cost"]
    vals = [owner_gain[idx_h] / 1e6, public_cost[idx_h] / 1e6]
    bars = axR.bar(labels, vals, color=[C_WARN, C_HARM], width=0.6)
    axR.set_ylabel(r"\$M in one scarcity window (240k-unit fleet)")
    axR.set_title("O10  Even a LEGAL profit-seeker is negative-sum\n"
                  rf"every \$1 the fleet earns costs Texas \${lever:,.0f}")
    for b, v in zip(bars, vals):
        axR.text(b.get_x() + b.get_width() / 2, v, f"  \\${v:,.0f}M",
                 ha="center", va="bottom", fontsize=10, fontweight="bold")
    axR.margins(y=0.20)
    annotate_defense(axR, "market power is paid on ALL load but earned on a\n"
                          "sliver -- screen fleet share of any scarcity interval")
    fig_path = savefig(fig, "O10_market_power.png")

    # ---- table ----
    header = ["fleet units", "fleet MW", "helpful $M", "withhold $M",
              "hostile $M", "hostile price $/MWh", "harm(hostile) $M"]
    rows = []
    for i, n in enumerate(sizes):
        rows.append([f"{int(n):,}", f"{F[i]:.0f}",
                     f"{cost_help[i]/1e6:,.1f}", f"{cost_rational[i]/1e6:,.1f}",
                     f"{cost_hostile[i]/1e6:,.1f}", f"{p_hostile[i]:,.0f}",
                     f"{harm_hostile[i]/1e6:,.1f}"])
    tab_path = write_table("O10_market_power.csv", header, rows)

    para = (
        f"O10 (market-making at scale is the harm): The three dispatch regimes in "
        f"research.tex differ only by the price each internalizes; the strategic fleet "
        f"withholds (p + Q*p') to hold price up -- that is market power. Priced out on a "
        f"real-structure ERCOT scarcity interval (~${p_scarcity:,.0f}/MWh, implied load "
        f"~{L/1000:,.0f} GW settling at the single clearing price), a hostile/compromised "
        f"240k-unit fleet ({fleet_mw(FLEET_HORIZON):,.0f} MW) inflates what ALL Texas load "
        f"pays in ONE 2-hour window by ~${harm_hostile[idx_h]/1e6:,.0f}M -- about "
        f"${per_hh_event:,.0f}/household/event (~${per_hh_summer:,.0f}/household over a "
        f"{SCARCITY_EVENTS_PER_SUMMER}-event summer). Today's 20k fleet moves it far less "
        f"(~${harm_hostile[0]/1e6:,.1f}M), so the harm is a consequence of SCALE: at "
        f"3x/yr growth the fleet crosses into systemic territory within ~2 years. And it "
        f"is negative-sum -- for every $1 the owner earns by withholding, ratepayers pay "
        f"~${lever:,.0f}, because the price is set at the margin but paid on all load. "
        f"Private gain != social good. DEFENSE: a per-scarcity fleet-share screen, the "
        f"cross-unit correlation detector (O6), and a no-coordinated-withhold rule under "
        f"low reserve (O7). [price STRUCTURE: ERCOT offer-cap scarcity reference, labeled]"
    )
    return {"fig": fig_path, "table": tab_path, "paragraph": para,
            "lever": lever, "harm_hostile_horizon_musd": float(harm_hostile[idx_h] / 1e6),
            "harm_hostile_today_musd": float(harm_hostile[0] / 1e6),
            "per_hh_event": float(per_hh_event), "p_scarcity": p_scarcity,
            "L_scarcity_gw": float(L / 1000.0)}


if __name__ == "__main__":
    out = run()
    print(out["paragraph"])
    print("figure:", out["fig"])
    print("table :", out["table"])
