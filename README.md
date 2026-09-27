# VPP Red-Team / Vulnerability Analysis

**Defensive** vulnerability map of a distributed battery Virtual Power Plant
(~20k units, ~20 kW / 40 kWh → ~400 MW / 800 MWh), requested by the fleet owner.
The deliverable is a set of **thresholds, price sensitivities, detection
signatures, and mitigations** — not an attack tool. Every offensive metric is
computed on **synthetic / representative topology** with a **generic anomaly
budget ε**, and is paired with its defense. See [`SPEC.md`](SPEC.md) for the
authoritative brief and [`research.tex`](research.tex) for the math backbone
(two graphs, three regimes, separability, impact bound).

## Punchline

There is **no "crash ERCOT" number** from a healthy grid. 400 MW is ~0.4% of an
~85–95 GW peak and the 2-hour energy budget forbids sustained action. The real,
bounded risks are (1) **local feeder concentration**, (2) **amplification of
already-critical intervals** (during a real EEA2 event a coordinated fleet swing
*can* be the marginal push into rolling blackouts), (3) **slow sub-threshold
efficiency erosion**, and (4) **inverter-switching hardware damage** — each capped
by a concrete bound and revealed by a monitorable signature.

## Your four questions → where they're answered

| Question | Output | Headline answer (real-data-anchored where possible) |
|---|---|---|
| **How many nodes to crash the system?** (stressed market, real ERCOT) | **O7** (+O1 local) | Crash = EEA3 **rolling blackouts** (PRC ≤ 1,430 MW). On today's **real** grid (min PRC ~9.2 GW) it takes **~195k nodes ≈ 10× the fleet**; at **EEA2 (~1,750 MW, real 2023‑09‑06 event)** only **~8k nodes (40% of the fleet)** — the fleet can tip an already-critical grid. Locally, **~108 nodes** overload one feeder. |
| **How many total nodes to crash the market/system?** | **O7** | The whole 20k fleet (400–800 MW swing) only becomes a system trigger when reserves are already below **~2,230 MW (≈EEA1)**. To crash a *normal* grid needs **O(10⁵) nodes (5–40×)**. Market price "crash" needs O(10⁵) nodes too — scarcity pins price at the cap on its own. |
| **Subtle ways to make things inefficient over time?** | **O9** | A persistent **sub-threshold** bias inflates cost (~$0.1–0.65M/day) and erodes efficiency invisibly per-interval; over 180 d undetected = **$18–117M**. A **sequential CUSUM** monitor bounds cumulative harm to **~$7M** regardless of how slow the attacker goes. |
| **Cyber attacks that damage batteries (inverter switching)?** | **O8** | Constant **1 Hz inverter switching** consumes IGBT power-cycling life in **~6 days** and battery life in months. A 5‑min dwell alone is insufficient (~5 yr); a **switching-count cap ≤ 48/day** restores ~32 yr and the switching frequency is a trivial telemetry alarm. |

## Quickstart

```bash
python -m pip install -r requirements.txt   # numpy/scipy/pandas/matplotlib required
python run_all.py                           # runs O1-O6, writes results/
```

Outputs land in `results/figures/*.png`, `results/tables/*.csv`, and a combined
`results/SUMMARY.md`. Each simulation is also runnable on its own, e.g.
`python -m sims.o1_feeder_threshold`.

> **Environment note.** `gridstatus` and `pandapower` do not build on Python 3.14
> (no wheels; lxml needs libxml2). The toolkit degrades gracefully:
> - **Prices:** `fetch_ercot.py` pulls **real ERCOT 15-min Load-Zone SPP** from
>   ERCOT's public real-time dashboard over plain HTTP — no `gridstatus`, no auth
>   — and caches a snapshot (`data/ercot_realtime_snapshot.csv`). Today's real
>   data anchors the **calm** interval; the **scarcity** anchor uses ERCOT's
>   documented $5,000/MWh offer-cap regime (β from the structural curve) unless a
>   live scarcity interval is present. `gridstatus` (Python ≤ 3.12) additionally
>   enables a real historical summer-scarcity scan. Every figure labels its
>   provenance.
> - **Feeder:** falls back to a representative radial tree with **LinDistFlow
>   implemented directly** (SPEC-sanctioned); `pandapower` (Python ≤ 3.12) enables
>   the canonical IEEE test feeders.

## Results at a glance (default run)

| Output | Result | Paired defense |
|---|---|---|
| **O1** local threshold | φ* ≈ **108** co-located 20 kW units (2.2 MW), thermal-bound — O(10²) | per-feeder cap ~75 units + synchronized-dispatch interlock |
| **O2** price sensitivity | scarcity/calm dP/dQ ratio ≈ **3000×+**; full fleet moves scarcity price ≤ **~13%** (~0.5% in calm); 400 MW = **0.44%** of peak, 2 h budget → **no system crash** (calm anchor is **real ERCOT** Load-Zone data) | no system MW cap needed; monitor scarcity; enforce local cap + detector |
| **O3** coordination premium | ≈ **1** below φ* (separable), rising steeply above | cap correlation + per-feeder penetration → premium collapses to ~1 |
| **O4** stealth frontier | harm(ε) monotone; detection near-certain at **ε\*≈0.25**, capping stealthy cost inflation | per-unit deviation alarm at ε\* |
| **O5** degradation | aging accel. up to ~7.4× at ε=1, **capped ~1.7×** by detection at ε\* | C-rate ≤0.5, DoD floor 10%, ≤2 EFC/day, ≥5 min dwell, ramp limit |
| **O6** detection + mitigation | correlation+bias ROC; mitigation set-point map | consolidated control set |
| **O7** system/market crash | rolling-blackout nodes vs starting reserve (real PRC + EEA3): ~10× fleet on a healthy grid, ~0.4× fleet at EEA2 | block coordinated charging under EEA/low-PRC + caps + detector |
| **O8** inverter-switching damage | 1 Hz switching kills inverter in ~6 days, battery in months | switching-count cap ≤48/day + min-dwell + ramp limit + frequency alarm |
| **O9** slow inefficiency over time | sub-threshold cost erosion; $18–117M/180d undetected | sequential CUSUM bounds cumulative harm to ~$7M |

(Exact numbers reprint on each run; synthetic-price runs are labeled as such.)

## How each acceptance criterion is met

- **Provenance.** `data/fetch_ercot.py` pulls **real ERCOT Load-Zone SPP** from
  the public dashboard (cached to `data/ercot_realtime_snapshot.csv`) and, where
  present, a `gridstatus` historical scarcity scan; the scarcity anchor otherwise
  uses ERCOT's documented $5,000/MWh offer-cap regime. Every figure and table
  states which parts are real vs reference.
- **O1 φ\*** is a concrete integer with a violation curve, O(10²) (see O1 table).
- **O2** prints the scarcity-vs-calm sensitivity ratio and an explicit numeric
  "no system crash" statement (fleet MW as % of peak, energy-limited sustain time).
- **O3** premium is exactly 1 below threshold (regularized ratio), then rises.
- **O4/O5** harm(ε) is monotone and overlaid with a stated detection ROC.
- **Solver status / first-order gap.** No iterative numerical optimizer is used:
  O1/O3 are **exhaustive integer sweeps** (exact over the grid), and O4's cost
  objective is affine so its ε-bounded maximum is the **closed-form corner**
  (exact; zero optimality gap). Where sweeps set a grid resolution, it is small
  relative to the reported effect (O1 to the unit; ε on a 0.05 grid).
- **Pairing.** Every figure is stamped with its `DEFENSE:` mitigation.

## Module map

```
data/fetch_ercot.py   real ERCOT SPP pull (gridstatus) + stressed/calm finder + labeled fallback
data/topology.py      representative radial feeder (LinDistFlow-ready); IEEE-123 via pandapower when present; super-node aggregation
models/price.py       inverse supply f(L), local sensitivity f'(L)=beta, anchored counterfactual
models/feasibility.py LinDistFlow branch flows + squared voltages + thermal/voltage violations (the set A_t)
models/degradation.py Wohler cycle life, rainflow EFC, C-rate/temperature multipliers, detection signature, protective bounds
models/adversary.py   J_cost / J_stress / J_degrade objectives + eps stealth budget (defensive threshold-finding only)
models/detection.py   diversification (correlation) + directional-bias statistic, ROC vs eps, monitoring thresholds
sims/o1..o5           local threshold, price sensitivity, coordination, stealth frontier, degradation
sims/o7_system_crash        nodes to rolling blackout vs real ERCOT reserve (EEA3) + market-price crash
sims/o8_inverter_switching  inverter/battery damage from constant switching + switching-frequency detection
sims/o9_slow_inefficiency   sub-threshold cost erosion over months + sequential (CUSUM) bound
run_all.py            runs O1-O9, assembles O6, writes results/SUMMARY.md
```

## Scope & guardrails

This repository implements the SPEC §0/§7 guardrails: representative/synthetic
topology only (no real asset is modeled or named); the degradation module
produces **sensitivity + detection signature + protective bounds, never a
destruction-optimal schedule**; ε is a **generic** anomaly bound, not tuned to
any real detector; and the framing is defensive throughout — every threshold
comes with the cap, bound, or detector that neutralizes it.
