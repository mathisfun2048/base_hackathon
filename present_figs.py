"""Presentation figures: one message per chart, plain language, quick-glance.

Reuses the same models and result tables as run_all.py, but redraws the key
risks for a short talk: the takeaway is the title, axes use everyday units, no
jargon, and defenses are left off (covered separately). The analyst figures in
results/figures/ are unchanged.

    python present_figs.py        # writes results/figures/presentation/*.png
"""
from __future__ import annotations

import csv
import os

import matplotlib as mpl
import numpy as np

from sims._common import ROOT, plt
from sims import o11b_feeder_map as o11b
from sims.o10_market_power import GROWTH_PER_YEAR
from data.topology import representative_feeder
from models import adversary, degradation, feasibility
from models.price import calibrate_to_observed, load_for_price

OUT_DIR = os.path.join(ROOT, "results", "figures", "presentation")
TAB_DIR = os.path.join(ROOT, "results", "tables")
os.makedirs(OUT_DIR, exist_ok=True)

FLEET_UNITS = 20_000
FLEET_MW = 400.0
UNIT_MW = 0.020

# palette: red = harm, dark blue = Base fleet / emphasis, gray = context
RED = "#C0392B"
BLUE = "#1F4E79"
GRAY = "#A6ACAF"
INK = "#1C2833"
MUTED = "#707B7C"

STYLE = {
    "figure.figsize": (11, 6.2),
    "figure.dpi": 100,
    "savefig.dpi": 220,
    "font.size": 14,
    "axes.titlesize": 21,
    "axes.titleweight": "bold",
    "axes.titlelocation": "left",
    "axes.titlepad": 34,
    "axes.labelsize": 14,
    "axes.labelcolor": INK,
    "axes.edgecolor": MUTED,
    "axes.grid": False,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "xtick.labelsize": 13,
    "ytick.labelsize": 13,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "legend.frameon": False,
    "text.color": INK,
    "text.parse_math": False,       # plain "$" in dollar labels
}


def _read_table(name):
    with open(os.path.join(TAB_DIR, name), newline="") as fh:
        return list(csv.DictReader(fh))


def _num(s):
    return float(str(s).replace(",", "").replace("$", ""))


def _headline(ax, title, subtitle):
    ax.set_title(title)
    ax.text(0, 1.035, subtitle, transform=ax.transAxes, fontsize=14,
            color=MUTED, ha="left", va="bottom")


def _source(fig, text):
    fig.text(0.01, -0.02, text, fontsize=9.5, color=MUTED, ha="left", va="top")


def _save(fig, name):
    path = os.path.join(OUT_DIR, name)
    fig.savefig(path, bbox_inches="tight", pad_inches=0.3, facecolor="white")
    plt.close(fig)
    return path


def fleet_scale():
    peak_mw = 90_000
    fig, ax = plt.subplots(figsize=(11, 3.6))
    ax.barh([0], [peak_mw], color=GRAY, height=0.55)
    ax.barh([0], [FLEET_MW], color=RED, height=0.55)
    ax.text(peak_mw / 2, 0, "Texas grid at summer peak  ~90,000 MW", ha="center",
            va="center", fontsize=15, color="white", fontweight="bold")
    ax.annotate(f"Base fleet: {FLEET_MW:.0f} MW  (0.4%)", xy=(FLEET_MW, 0.28),
                xytext=(6_000, 0.62), fontsize=15, color=RED, fontweight="bold",
                arrowprops=dict(arrowstyle="-|>", color=RED, lw=1.6))
    ax.set_xlim(0, peak_mw)
    ax.set_ylim(-0.45, 0.8)
    ax.axis("off")
    _headline(ax, "The whole fleet is 0.4% of Texas demand",
              "20,000 batteries x 20 kW = 400 MW, and only 2 hours of stored energy")
    return _save(fig, "01_fleet_scale.png")


def neighborhood_threshold():
    fdr = representative_feeder()
    node = fdr.coloc_node
    path = fdr.path_to_root(node)
    homes = np.arange(0, 251)
    loading = []
    for n in homes:
        q = feasibility.inject_at(fdr, node, -n * UNIT_MW)     # all charging together
        P, R = feasibility.branch_flows(fdr, q)
        K = feasibility.thermal_limits(fdr, R)
        loading.append(max(abs(P[e]) / K[e] for e in path if e != 0) * 100)
    loading = np.array(loading)
    first_over = int(homes[np.argmax(loading > 100)])
    archetypes = [int(r["phi* (units)"]) for r in _read_table("O11_topology_sensitivity.csv")]

    fig, ax = plt.subplots()
    ax.axhspan(100, loading.max() * 1.08, color=RED, alpha=0.07, lw=0)
    ax.axhline(100, color=RED, lw=1.4, ls="--")
    ax.text(3, 103, "wire's safe limit", color=RED, fontsize=13, va="bottom")
    ax.plot(homes, loading, color=BLUE, lw=3.2)
    ax.plot([first_over], [loading[first_over]], "o", color=RED, ms=11, zorder=5)
    ax.annotate(f"{first_over} homes\noverload it", xy=(first_over, loading[first_over]),
                xytext=(first_over - 70, loading[first_over] + 45), fontsize=16,
                color=RED, fontweight="bold",
                arrowprops=dict(arrowstyle="-|>", color=RED, lw=1.6))
    ax.set_xlim(0, homes[-1])
    ax.set_ylim(0, loading.max() * 1.08)
    ax.set_xlabel("battery homes on one street, all charging at once")
    ax.set_ylabel("load on the shared wire (% of its limit)")
    ax.yaxis.set_major_formatter(mpl.ticker.PercentFormatter(decimals=0))
    _headline(ax, f"About {first_over} batteries acting together overload a neighborhood",
              f"Hundreds, not thousands. Across street types it takes "
              f"{min(archetypes)}-{max(archetypes)}.")
    _source(fig, "Representative (synthetic) 12.47 kV feeder with a 3 MVA shared segment; "
                 "no real circuit modeled.")
    return _save(fig, "02_neighborhood_overload.png")


def neighborhood_map():
    fdr, block_homes, _ = o11b.neighborhood_feeder()
    pos = o11b.tree_layout(fdr)
    cmap, norm = mpl.cm.RdYlGn_r, mpl.colors.Normalize(0.0, 1.2)

    fig, axes = plt.subplots(1, 3, figsize=(15, 6.2), constrained_layout=True)
    for ax, phi in zip(axes, [50, 150, 240]):
        o11b.draw(ax, fdr, block_homes, phi, pos, cmap, norm)
        for t in list(ax.texts):        # drop the analyst labels; retitle below
            t.remove()
        ax.set_title("", loc="left")
        ax.annotate("substation", pos[0], textcoords="offset points", xytext=(0, 14),
                    ha="center", fontsize=11, color=MUTED)
        q = np.zeros(fdr.N)
        q[block_homes] = -phi / len(block_homes) * UNIT_MW
        P, R = feasibility.branch_flows(fdr, q)
        K = feasibility.thermal_limits(fdr, R)
        peak = float((np.abs(P[1:]) / K[1:]).max())
        over = peak > 1.0
        ax.set_title(f"{phi} battery homes\n"
                     + (f"shared wire at {peak:.0%}: OVERLOADED" if over
                        else f"shared wire at {peak:.0%}: fine"),
                     fontsize=15, loc="center", pad=8, fontweight="bold",
                     color=RED if over else INK)
    sm = mpl.cm.ScalarMappable(cmap=cmap, norm=norm)
    cbar = fig.colorbar(sm, ax=axes, orientation="horizontal", fraction=0.045, pad=0.02,
                        aspect=50)
    cbar.set_ticks([0, 0.5, 1.0, 1.2])
    cbar.set_ticklabels(["0%", "50%", "100% = limit", "120%+"])
    cbar.ax.tick_params(labelsize=12)
    cbar.set_label("how hard each wire is working (blue squares = battery homes)", fontsize=12)
    fig.suptitle("No single home is the problem: the shared wire feeding the block overloads",
                 fontsize=21, fontweight="bold", x=0.01, ha="left")
    fig.text(0.01, -0.03, "Representative (synthetic) neighborhood feeder; no real circuit "
             "modeled.", fontsize=9.5, color=MUTED)
    return _save(fig, "03_neighborhood_map.png")


def _time_to_reach(units):
    """Plain-language time for the fleet to grow to `units` at GROWTH_PER_YEAR."""
    if units <= FLEET_UNITS:
        return "Base is already there"
    years = np.log(units / FLEET_UNITS) / np.log(GROWTH_PER_YEAR)
    if years >= 1:
        return f"Base reaches it in ~{years:.0f} years" if round(years) > 1 else "Base reaches it in ~1 year"
    months = max(1, round(years * 12))
    return f"Base reaches it in ~{months} month{'s' if months > 1 else ''}"


def blackout_threshold():
    rows = {r["grid condition"]: r for r in _read_table("O7_system_crash.csv")}
    items = [
        ("Today", "Today minimum (REAL)"),
        ("Emergency watch", "EEA Watch"),
        ("Emergency level 1", "EEA1"),
        ("Emergency level 2\n(Sept 6, 2023)", "EEA2 = Summer 2023-09-06 (documented)"),
    ]
    labels = [lab for lab, _ in items]
    needed = np.array([_num(rows[key]["nodes @40kW swing"]) for _, key in items])

    fig, ax = plt.subplots()
    y = np.arange(len(items))[::-1]
    colors = [RED if n <= FLEET_UNITS else GRAY for n in needed]
    ax.barh(y, needed / 1e3, color=colors, height=0.62)
    for yi, n in zip(y, needed):
        txt = f"{n/1e3:,.0f}k  ({_time_to_reach(n)})"
        ax.text(n / 1e3 + 4, yi, txt, va="center", fontsize=13,
                color=RED if n <= FLEET_UNITS else INK,
                fontweight="bold" if n <= FLEET_UNITS else "normal")
    ax.axvline(FLEET_UNITS / 1e3, color=BLUE, lw=2.2)
    ax.text(FLEET_UNITS / 1e3 + 3, y[0] + 0.52, "Base fleet today: 20k", color=BLUE,
            fontsize=13, fontweight="bold", va="bottom")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, color=INK)
    ax.tick_params(axis="y", length=0)
    ax.set_xlim(0, needed.max() / 1e3 * 1.32)
    ax.set_ylim(-0.6, len(items) - 0.2)
    ax.set_xlabel("batteries needed to trigger rolling blackouts (thousands)")
    _source(fig, "Blackout = ERCOT firm load shed (reserves <= 1,430 MW). 'Today' uses "
                 "real ERCOT reserve data (tightest point); emergency levels use ERCOT's defined thresholds.\n"
                 f"Time to reach assumes the Base fleet keeps growing {GROWTH_PER_YEAR:.0f}x per year "
                 f"from {FLEET_UNITS:,} units today.")
    return _save(fig, "04_blackout_threshold.png")


def price_spike_cost():
    rows = _read_table("O10_market_power.csv")
    show = ["20,000", "40,000", "80,000", "120,000", "240,000"]
    rows = [r for r in rows if r["fleet units"] in show]
    units = [int(_num(r["fleet units"])) for r in rows]
    harm = np.array([_num(r["harm(hostile) $M"]) for r in rows])

    fig, ax = plt.subplots()
    x = np.arange(len(rows))
    colors = [RED if u in (20_000, 240_000) else GRAY for u in units]
    ax.bar(x, harm, color=colors, width=0.62)
    for xi, h in zip(x, harm):
        ax.text(xi, h + 12, f"${h:,.0f}M", ha="center", fontsize=15, fontweight="bold",
                color=INK)
    names = {20_000: "20k\n(today)", 240_000: "240k\n(~2 years out)"}
    ax.set_xticks(x)
    ax.set_xticklabels([names.get(u, f"{u//1000}k") for u in units], color=INK)
    ax.tick_params(axis="x", length=0)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_ylim(0, harm.max() * 1.18)
    ax.set_xlabel("fleet size (batteries)")
    hh = harm[-1] * 1e6 / 10_000_000
    _headline(ax, f"One hijacked price spike: ${harm[0]:,.0f}M today, ${harm[-1]:,.0f}M at 240k",
              f"Extra paid by all Texas customers in a single 2-hour scarcity window "
              f"(~${hh:,.0f} per household at 240k)")
    _source(fig, "Hostile control = charging during scarcity to push price up. Price structure: "
                 "ERCOT $5,000/MWh offer-cap scarcity reference (~$2,500/MWh starting price).")
    return _save(fig, "05_price_spike_cost.png")


def inverter_lifetime():
    scenarios = [
        ("Normal operation\n(~6 flips a day)", 6),
        ("Flip every 5 minutes", 288),
        ("Flip every minute", 1_440),
        ("Flip every second", 86_400),
    ]
    days = np.array([degradation.inverter_switching_wear(r)["inverter_life_years"] * 365
                     for _, r in scenarios])
    labels = [s for s, _ in scenarios]

    fig, ax = plt.subplots()
    y = np.arange(len(scenarios))[::-1]
    for yi, d in zip(y, days):
        col = RED if d < 365 * 2 else GRAY if d > 365 * 15 else INK
        ax.hlines(yi, 1, d, color=col, lw=5)
        ax.plot(d, yi, "o", color=col, ms=14)
        txt = ("outlasts the unit" if d > 365 * 15 else
               f"~{d/365:.0f} years" if d >= 365 * 1.5 else
               f"~{d/365:.0f} year" if d >= 365 else f"~{d:.0f} days")
        ax.text(d * 1.35, yi, txt, va="center", fontsize=16, fontweight="bold", color=col)
    ax.axvline(15 * 365, color=MUTED, ls=":", lw=1.4)
    ax.text(15 * 365 * 1.1, y[-1] - 0.45, "15-yr design life", color=MUTED, fontsize=12)
    ax.set_xscale("log")
    ax.set_xlim(1, 365 * 3_000)
    ax.set_xticks([1, 7, 30, 365, 365 * 10, 365 * 100])
    ax.set_xticklabels(["1 day", "1 week", "1 month", "1 year", "10 years", "100 years"])
    ax.xaxis.set_minor_locator(mpl.ticker.NullLocator())
    ax.set_yticks(y)
    ax.set_yticklabels(labels, color=INK)
    ax.tick_params(axis="y", length=0)
    ax.set_ylim(-0.8, len(scenarios) - 0.4)
    ax.set_xlabel("how long the inverter lasts")
    _headline(ax, "Rapid charge/discharge flipping wears out inverters in about a week",
              "Each flip heats and cools the power electronics; rapid flipping piles up "
              "that fatigue")
    _source(fig, "Power-electronics fatigue model (Coffin-Manson), generic residential "
                 "20 kW inverter; not tied to any specific product.")
    return _save(fig, "06_inverter_lifetime.png")


def slow_drain():
    p_peak = 150.0
    L0 = load_for_price(p_peak)
    cal = calibrate_to_observed(p_peak, L0)
    L, Qb = np.full(4, L0), np.zeros(4)
    nudges = [(0.03, GRAY), (0.10, INK), (0.20, RED)]
    days = np.arange(0, 366)

    fig, ax = plt.subplots()
    top = 0
    for eps, col in nudges:
        per_day = adversary.max_cost_harm_within_eps(L, cal["price"], Qb,
                                                     eps * FLEET_MW)["harm"] / 1e6
        cum = days * per_day
        top = max(top, cum[-1])
        ax.plot(days, cum, color=col, lw=3.2)
        ax.text(days[-1] + 6, cum[-1], f"{eps:.0%} nudge: ${cum[-1]:,.0f}M",
                va="center", fontsize=15, fontweight="bold", color=col)
    ax.set_xlim(0, 365)
    ax.set_ylim(0, top * 1.08)
    ax.set_xticks([0, 91, 182, 273, 365])
    ax.set_xticklabels(["start", "3 months", "6 months", "9 months", "1 year"])
    ax.set_ylabel("extra cost to Texas customers ($M)")
    ax.yaxis.set_major_formatter(mpl.ticker.StrMethodFormatter("${x:,.0f}M"))
    _headline(ax, "Small nudges nobody notices add up to real money",
              "Every battery drifts a few % off its best schedule during the daily peak hour; "
              "each step looks normal")
    _source(fig, "Nudge = each battery's deviation from its planned output, as a share of its "
                 "20 kW rating. Routine ~$150/MWh daily peak, ~1 hour/day.")
    return _save(fig, "07_slow_drain.png")


def main():
    with plt.rc_context(STYLE):
        paths = [fleet_scale(), neighborhood_threshold(), neighborhood_map(),
                 blackout_threshold(), price_spike_cost(), inverter_lifetime(),
                 slow_drain()]
    for p in paths:
        print(os.path.relpath(p, ROOT))


if __name__ == "__main__":
    main()
