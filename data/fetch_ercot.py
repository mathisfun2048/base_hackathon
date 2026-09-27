"""ERCOT real-time price access + stressed/calm interval finder (SPEC S3).

Primary path (when `gridstatus` is installed, Python <= 3.12):
    Ercot().get_spp(date=..., market=Markets.REAL_TIME_15_MIN,
                    location_type="Load Zone")
Settle at LOAD ZONE (not a hub average) for a residential fleet -- the paper's
ERCOT-anchoring section is explicit that a hub average is a proxy, not the
fleet's actual settlement exposure.

Products (for provenance in the writeup):
    SPP 15-min             NP6-905-CD
    SCED LMP 5-min         NP6-788-CD
    historical RTM hub/zone NP6-785-ER

Fallback (this environment: no gridstatus wheel on Python 3.14): a clearly
labeled, calibrated scarcity/off-peak price path with an ORDC/ASDC-style kink.
Every figure built from the fallback is stamped "calibrated synthetic".

Market-vintage note (research.tex): RTC+B went live 2025-12-05 and ASDC
replaced the legacy ORDC adder at that transition. The scarcity shape here is a
reduced-form ORDC/ASDC-style adder, not the live clearing engine.
"""
from __future__ import annotations

from dataclasses import dataclass
import datetime as _dt
import json as _json
import os as _os
import ssl as _ssl
import urllib.request as _url
import numpy as np

from models.price import inverse_supply, OFFER_CAP

# ERCOT public real-time dashboard (no auth, no gridstatus): system-wide prices
# with per-Load-Zone SPP at 15-min resolution for the current operating day.
ERCOT_RT_DASHBOARD = "https://www.ercot.com/api/1/services/read/dashboards/systemWidePrices.json"
ERCOT_PRC_DASHBOARD = "https://www.ercot.com/api/1/services/read/dashboards/daily-prc.json"
DEFAULT_ZONE = "lzNorth"       # a major ERCOT Load Zone (settle at zone, not hub)
_CACHE = _os.path.join(_os.path.dirname(__file__), "ercot_realtime_snapshot.csv")
_PRC_CACHE = _os.path.join(_os.path.dirname(__file__), "ercot_prc_snapshot.csv")

# ERCOT Energy Emergency Alert (EEA) reserve thresholds on Physical Responsive
# Capability (PRC), MW. Public ERCOT operating levels; EEA3 = firm load shed
# (rotating/rolling blackouts). Source: ERCOT EEA process / Nodal Operating Guide.
EEA_THRESHOLDS = {
    "EEA Watch": 3000.0,   # projected shortage; conservation appeals
    "EEA1": 2300.0,        # reserves below 2,300 MW
    "EEA2": 1750.0,        # reserves below 1,750 MW
    "EEA3": 1430.0,        # reserves below 1,430 MW -> ROLLING BLACKOUTS (firm load shed)
}
ROLLING_BLACKOUT_PRC = EEA_THRESHOLDS["EEA3"]

# Documented real ERCOT stress events (public post-event reports), used as the
# "already-stressed market" anchors. Values are approximate, cited, and labeled.
DOCUMENTED_EVENTS = {
    "Winter Storm Uri (2021-02)": {
        "prc_mw": 1000.0,          # PRC collapsed near/below EEA3; ~20 GW firm load shed
        "load_shed_mw": 20000.0,   # peak firm load shed
        "freq_hz": 59.40,          # held ~4m37s; ~9 min from cascading collapse
        "offer_cap": 9000.0,       # HCAP in 2021 (lowered to $5,000 in 2023)
        "note": "EEA3; rotating outages; FERC/NERC & ERCOT post-event reports",
    },
    "Summer heat EEA2 (2023-09-06)": {
        "prc_mw": 1750.0,          # first EEA2 since Uri; reserves < 1,750 MW
        "load_shed_mw": 0.0,       # no firm shed; EEA2 conservation
        "offer_cap": 5000.0,       # current HCAP
        "note": "ERCOT EEA Level 2; RTM prices reached the $5,000 offer cap",
    },
}


# ---------------------------------------------------------------------------
# Documented public reference anchors (used only by the calibrated fallback).
# These are representative of published ERCOT behavior, NOT a specific
# reconstructed interval, and are labeled synthetic wherever they surface.
# ---------------------------------------------------------------------------
REF_STRESSED_PRICE = 2500.0   # $/MWh: representative RT scarcity (adder active)
REF_CALM_PRICE = 28.0         # $/MWh: representative off-peak RT
REF_OFFER_CAP = OFFER_CAP     # $/MWh: ERCOT system-wide offer cap


@dataclass
class PriceInterval:
    label: str                # "stressed" | "calm"
    date: str                 # ISO date, "synthetic", or "scarcity-reference"
    price_series: np.ndarray  # $/MWh over the day (15-min)
    peak_price: float         # $/MWh at the scarcity/peak interval
    location_type: str        # "Load Zone"
    source: str               # provenance string

    @property
    def real(self) -> bool:
        """True when this interval is measured ERCOT data (not synthetic/reference)."""
        s = self.source.upper()
        return s.startswith("REAL") or "GRIDSTATUS" in s


def gridstatus_available() -> bool:
    try:
        import gridstatus  # noqa: F401
        return True
    except Exception:
        return False


def fetch_spp(date, location_type: str = "Load Zone", location: str | None = None):
    """Real SPP pull via gridstatus (15-min RTM). Raises if unavailable.

    Returns a tidy DataFrame [Interval Start, Location, SPP]. Caller filters to
    a single load zone.
    """
    import gridstatus
    from gridstatus import Ercot, Markets

    iso = Ercot()
    df = iso.get_spp(date=date, market=Markets.REAL_TIME_15_MIN,
                     location_type=location_type)
    if location is not None:
        df = df[df["Location"] == location]
    return df


def fetch_realtime_dashboard(zone: str = DEFAULT_ZONE, timeout: int = 25):
    """Pull today's REAL ERCOT 15-min Load-Zone SPP from the public dashboard.

    No gridstatus / no auth. Returns (prices[np.ndarray], date_str, last_updated,
    zone) and caches a CSV snapshot for reproducibility. Raises on any failure so
    callers can fall back.
    """
    ctx = _ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = _ssl.CERT_NONE
    req = _url.Request(ERCOT_RT_DASHBOARD, headers={"User-Agent": "Mozilla/5.0"})
    data = _json.load(_url.urlopen(req, timeout=timeout, context=ctx))
    rt = data.get("rtSppData", [])
    prices = np.array([float(r[zone]) for r in rt if zone in r], dtype=float)
    if prices.size < 8:
        raise RuntimeError("insufficient real-time intervals returned")
    last_updated = str(data.get("lastUpdated", ""))
    date_str = last_updated.split(" ")[0] if last_updated else _dt.date.today().isoformat()
    try:
        with open(_CACHE, "w", newline="") as fh:
            fh.write(f"# ERCOT RTM 15-min SPP, Load Zone {zone}, {date_str}; "
                     f"pulled {last_updated}; source {ERCOT_RT_DASHBOARD}\n")
            fh.write("interval,price_usd_per_mwh\n")
            for i, p in enumerate(prices):
                fh.write(f"{i},{p}\n")
    except OSError:
        pass
    return prices, date_str, last_updated, zone


def fetch_prc(timeout: int = 25) -> dict:
    """Pull today's REAL ERCOT Physical Responsive Capability (PRC) series.

    PRC is the reserve metric ERCOT uses to declare Energy Emergency Alerts; it is
    the physical "how close to rolling blackouts" signal. Returns current PRC,
    today's series, today's minimum and 5th-percentile (the tail / p95-stress
    reserve), plus provenance. Caches a snapshot. Raises on failure.
    """
    ctx = _ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = _ssl.CERT_NONE
    req = _url.Request(ERCOT_PRC_DASHBOARD, headers={"User-Agent": "Mozilla/5.0"})
    d = _json.load(_url.urlopen(req, timeout=timeout, context=ctx))
    series = np.array([float(p["prc"]) for p in d.get("data", [])
                       if isinstance(p, dict) and p.get("prc") is not None], dtype=float)
    if series.size < 10:
        raise RuntimeError("insufficient PRC points")
    cur = d.get("current_condition", {})
    cur_prc = float(str(cur.get("prc_value", series[-1])).replace(",", ""))
    last_updated = str(d.get("lastUpdated", ""))
    date_str = last_updated.split(" ")[0] if last_updated else _dt.date.today().isoformat()
    p5 = float(np.percentile(series, 5))        # tight tail (p95-stress reserve)
    try:
        with open(_PRC_CACHE, "w", newline="") as fh:
            fh.write(f"# ERCOT PRC (Physical Responsive Capability) MW, {date_str}; "
                     f"pulled {last_updated}; source {ERCOT_PRC_DASHBOARD}\n")
            fh.write("index,prc_mw\n")
            for i, v in enumerate(series):
                fh.write(f"{i},{v}\n")
    except OSError:
        pass
    return {
        "current_prc_mw": cur_prc,
        "series": series,
        "today_min_mw": float(series.min()),
        "today_p5_mw": p5,
        "today_median_mw": float(np.median(series)),
        "eea_level_now": int(cur.get("eea_level", 0)),
        "date": date_str,
        "last_updated": last_updated,
        "source": (f"REAL ERCOT PRC dashboard, {date_str} (pulled {last_updated}); "
                   f"{ERCOT_PRC_DASHBOARD}"),
    }


def _synthetic_day(peak_price: float, calm: bool, T: int = 96, seed: int = 1):
    """Build a 15-min price path. Calm: flat off-peak. Stressed: ORDC-style
    afternoon scarcity kink anchored so its peak equals `peak_price`."""
    rng = np.random.default_rng(seed)
    hours = np.arange(T) * 0.25
    if calm:
        base = REF_CALM_PRICE + 6.0 * np.sin((hours - 6) / 24 * 2 * np.pi)
        noise = rng.normal(0, 1.5, T)
        return np.clip(base + noise, 8.0, None)
    # stressed: broad diurnal load + sharp late-afternoon scarcity adder
    load = 60_000 + 22_000 * np.exp(-((hours - 17.5) ** 2) / (2 * 2.2 ** 2))
    p = inverse_supply(load)
    # scale so the peak matches the reference scarcity price
    p = p * (peak_price / p.max())
    return np.clip(p + rng.normal(0, 5.0, T), 10.0, REF_OFFER_CAP)


SCARCITY_THRESHOLD = 500.0     # $/MWh above which we treat a real interval as scarce


def find_stressed_interval(start=None, end=None, location: str | None = None,
                           zone: str = DEFAULT_ZONE):
    """Return (stressed, calm) PriceIntervals, preferring REAL ERCOT data.

    Priority:
      1) gridstatus historical summer scan (real stressed + real calm), if installed.
      2) Public real-time dashboard (real Load-Zone SPP for today) -> real CALM.
         If today's real data itself contains scarcity (>$500), use it as a real
         stressed interval too; otherwise pair the real calm day with the
         documented ERCOT offer-cap scarcity reference (labeled) for the stressed
         anchor, whose beta comes from the structural inverse-supply curve.
      3) Fully calibrated synthetic (labeled), if offline.
    """
    # ---- 1) gridstatus historical (best: real scarcity + real calm) ----
    if gridstatus_available():
        try:
            year = _dt.date.today().year
            best = calm = None
            for m, d in [(8, 15), (8, 10), (7, 20), (9, 5), (6, 25)]:
                try:
                    df = fetch_spp(_dt.date(year, m, d), "Load Zone", location)
                except Exception:
                    continue
                pmax, pmed = float(df["SPP"].max()), float(df["SPP"].median())
                if best is None or pmax > best[0]:
                    best = (pmax, f"{year}-{m:02d}-{d:02d}", df["SPP"].to_numpy())
                if calm is None or pmed < calm[0]:
                    calm = (pmed, f"{year}-{m:02d}-{d:02d}", df["SPP"].to_numpy())
            if best and calm:
                src = "ERCOT SPP RTM 15-min (NP6-905-CD), Load Zone, via gridstatus"
                return (PriceInterval("stressed", best[1], best[2], best[0], "Load Zone", src),
                        PriceInterval("calm", calm[1], calm[2], float(np.median(calm[2])),
                                      "Load Zone", src))
        except Exception:
            pass

    # ---- 2) public real-time dashboard (real Load-Zone data, no gridstatus) ----
    try:
        prices, date_str, last_updated, z = fetch_realtime_dashboard(zone)
        real_src = (f"REAL ERCOT RTM 15-min SPP dashboard, Load Zone {z}, {date_str} "
                    f"(pulled {last_updated}); {ERCOT_RT_DASHBOARD}")
        calm_iv = PriceInterval("calm", date_str, prices, float(np.median(prices)),
                                f"Load Zone {z}", real_src)
        if float(prices.max()) >= SCARCITY_THRESHOLD:
            # today itself is scarce -> fully real contrast
            stressed_iv = PriceInterval("stressed", date_str, prices,
                                        float(prices.max()), f"Load Zone {z}", real_src)
        else:
            # no live scarcity: pair real calm with the documented scarcity reference
            ref_src = ("ERCOT offer-cap scarcity reference (representative of published "
                       "summer scarcity; $5,000/MWh offer cap); beta from structural "
                       "inverse-supply curve. Real calm data paired.")
            stressed_series = _synthetic_day(REF_STRESSED_PRICE, calm=False)
            stressed_iv = PriceInterval("stressed", "scarcity-reference", stressed_series,
                                        REF_STRESSED_PRICE, f"Load Zone {z}", ref_src)
        return stressed_iv, calm_iv
    except Exception:
        pass

    # ---- 3) fully synthetic fallback (offline) ----
    src = ("CALIBRATED SYNTHETIC (no network / gridstatus); peaks representative of "
           "published ERCOT summer scarcity vs off-peak, capped at $5,000/MWh offer cap")
    return (PriceInterval("stressed", "synthetic", _synthetic_day(REF_STRESSED_PRICE, False),
                          REF_STRESSED_PRICE, "Load Zone", src),
            PriceInterval("calm", "synthetic", _synthetic_day(REF_CALM_PRICE, True),
                          REF_CALM_PRICE, "Load Zone", src))


if __name__ == "__main__":
    s, c = find_stressed_interval()
    print(f"gridstatus available: {gridstatus_available()}")
    print(f"stressed: {s.date}  peak={s.peak_price:.1f} $/MWh  src={s.source[:48]}...")
    print(f"calm    : {c.date}  med ={c.peak_price:.1f} $/MWh")
