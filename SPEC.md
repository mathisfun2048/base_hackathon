# SPEC — VPP Red-Team / Vulnerability Analysis

## 0. What this is, and the guardrails

Red-team vulnerability mapping of a distributed battery VPP (~20k units,
~20 kW / 40 kWh each → ~400 MW / 800 MWh), **requested by the fleet owner for
defense**. The deliverable is a set of thresholds, sensitivities, detection
signatures, and mitigations — **not an attack tool**.

**Hard guardrails (enforced in every module):**

- Representative / synthetic topology only (published test feeders). Never model
  or name a real substation, circuit, or asset.
- Degradation work computes sensitivity + detection signature + protective
  bounds, **not** an optimized destruction schedule against real
  hardware/firmware.
- No evasion tuned to a specific real detector. The stealth budget `ε` is a
  generic anomaly bound, used to measure the stealth/impact frontier and to set
  mitigation thresholds.
- Framing throughout: "make the grid better, never worse." Every offensive
  result is paired with its defense.

## 1. Thesis being tested

Leverage over price and grid = endogenous price (β) + shared network limits (G₁)
+ detection budget (ε), and it switches on at a scale threshold. Below threshold
the problem is separable → an adversary gains nothing from coordination. The
whole build is: find the thresholds, and show the detectable signature.

**Key expected punchline:** There is no "crash ERCOT" number — 400 MW is ~0.4%
of an 85–95 GW peak, and the 2-hour energy budget forbids sustained action. The
real threat is local (feeder concentration) and amplification of already-stressed
intervals, not system collapse.

## 2. Outputs (each is one figure/table + a paragraph)

- **O1 — Local physical threshold.** On a representative feeder, sweep co-located
  unit count / penetration φ; find φ* where synchronized charge/discharge first
  violates thermal or voltage limits (`A_t`). Report as units-per-feeder relative
  to transformer rating (expected O(10²), not O(10⁴)).
- **O2 — Price sensitivity under stress vs calm.** Using ERCOT data, estimate
  local dP/dQ = −f′(L) on a stressed interval vs a calm one. Show leverage ≈ 0 in
  normal hours and only marginal under scarcity. Establish there is no system
  crash from the fleet's MW.
- **O3 — Correlation premium.** harm(coordinated)/harm(independent) vs φ. ≈ 1 at
  low φ (separability), > 1 only past a threshold. Mirror of the owner-side
  coordination premium ρ.
- **O4 — Stealth frontier.** Max harm (cost inflation and/or degradation) subject
  to the per-interval detectability budget ε; trace harm(ε). The knee is the
  mitigation set-point.
- **O5 — Degradation vulnerability + detection (defensive).** Using a public
  DoD/throughput/C-rate/temperature aging model, quantify how much a compromised
  controller could accelerate fleet aging within ε, the telemetry signature that
  reveals it, and the firmware/operational bounds that cap it. No
  destruction-optimal schedule.
- **O6 — Detection + mitigation summary.** The correlation statistic, per-feeder
  penetration caps, and telemetry-deviation bounds that map to ε.

## 2b. Additional outputs (handoff clarification)

Explicit metrics requested after the initial build; all keep the §0/§7 guardrails
(defensive, representative data, mitigations paired):

- **O7 — Nodes to crash the system / market.** Define "crash" as **rolling
  blackouts** = ERCOT EEA3 firm load shed (PRC ≤ 1,430 MW). Anchor to **real
  ERCOT PRC** (reserve) data plus documented stress events (Winter Storm Uri
  2021; the 2023‑09‑06 EEA2). Report coordinated nodes required as a function of
  the starting reserve (p95-tail / already-stressed view), and the market-price
  analogue (nodes to drive price to the offer cap). Mitigation: forbid coordinated
  charging under EEA/low-PRC.
- **O8 — Inverter-switching hardware-damage attack.** Quantify battery + power-
  electronics wear from constant charge/discharge switching (Coffin-Manson IGBT
  power cycling + battery micro-cycling), the switching-frequency detection
  signature, and the switching-count / min-dwell / ramp bounds that cap it.
- **O9 — Subtle inefficiency over time.** Persistent sub-threshold cost/efficiency
  erosion; show a sequential (CUSUM) detector bounds cumulative harm regardless of
  stealth level.

## 3. Data

**Primary: ERCOT real-time prices.**

- Settlement Point Prices, 15-min: product NP6-905-CD.
- SCED LMPs, 5-min: product NP6-788-CD.
- Historical RTM hub/zone prices: NP6-785-ER.
- Use `gridstatus` first (`data/fetch_ercot.py`):
  `Ercot().get_spp(date=..., market=Markets.REAL_TIME_15_MIN, location_type=...)`.
  Settle at **Load Zone**, not a hub average.
- Find a stressed interval: scan recent summer days (Jun–Sep) for the
  highest-price / scarcity intervals. Keep one stressed day + one calm day.
- Fallback (if MIS retention blocks the pull): a documented calibrated scarcity
  price path with an ORDC-like kink (`models/price.py`); labeled synthetic.

**Topology: published representative distribution feeders.**

- IEEE 123-node test feeder (radial, canonical) for O1. Use `pandapower` or
  implement LinDistFlow directly on the radial tree.
- For system-level context, aggregate the fleet into super-nodes (~5k cohorts).

## 4. Models (`models/`)

- `price.py` — inverse supply `f(L)` = merit-order slope + convex ORDC/ASDC
  scarcity adder capped at offer cap; `fprime(L)` = local price sensitivity.
  Calibrate to the real stressed interval (anchor `f(L_obs)=p_obs`).
- `feasibility.py` — LinDistFlow on the radial feeder: branch flows `P_e`,
  squared voltages `v_n`, thermal `|P_e|≤K_e`, voltage `V_min²≤v_n≤V_max²`.
  `violations(q)` returns which constraints bind/break.
- `degradation.py` — public aging model: DoD-dependent cycle life
  `N(DoD) ≈ a·DoD^(−b)`, equivalent full cycles via rainflow, C-rate and
  temperature multipliers; `aging_rate` / `aging_from_soc` and
  `detection_signature`. Reference NREL BLAST / LFP curves.
- `adversary.py` — objectives on the SAME graphs: `J_cost` (cost inflation),
  `J_stress` (feeder violation), `J_degrade` (aging); stealth constraint
  `‖q − q^benign‖ ≤ ε`. Defensive use only.
- `detection.py` — benign (diversified, decorrelated) vs adversarial (persistent
  correlation + directional bias) classifier; monitorable statistic + ROC vs ε.

## 5. Repo layout

```
vpp-redteam/
  SPEC.md  README.md  requirements.txt
  data/    fetch_ercot.py  topology.py
  models/  price.py  feasibility.py  degradation.py  adversary.py  detection.py
  sims/    o1_feeder_threshold.py  o2_price_sensitivity.py  o3_coord_vs_indep.py
           o4_stealth_frontier.py  o5_degradation.py
  results/{figures,tables}/
  run_all.py
```

## 6. Acceptance criteria

- Every quantitative claim traces to real ERCOT numbers (date/provenance) or a
  clearly-labeled calibrated fallback.
- O1 yields a concrete φ* per feeder with a violation curve; O(10²) local scale.
- O2 shows dP/dQ orders of magnitude larger in scarcity than calm; explicit "no
  system crash" statement backed by the number.
- O3 harm ratio ≈ 1 below threshold, rising above it.
- O4/O5 produce monotone harm(ε) frontiers and a detection statistic that
  separates adversarial from benign with a stated ROC.
- Optimizations report a solver status / first-order gap; tolerances small
  relative to any claimed effect.
- Each offensive figure is paired with its mitigation (cap, bound, or detector).

## 7. Non-goals (do not build)

- No optimized schedule to maximize irreversible hardware damage to a real fleet.
- No detector-evasion tuned to a specific real monitoring system.
- No real-asset / real-substation targeting or geolocation.
- No "hold infrastructure hostage" scenario. Defensive framing only.

## 8. Reference context (for the writeup)

- Fleet: ~20k units, ~20 kW / 40 kWh, two-hour asset → energy budget is the
  binding self-limit on sustained action.
- Market: energy-only ERCOT; 5-min SCED, 15-min settlement; RTC+B live since
  Dec 2025; ORDC adders replaced by ASDC with that transition.
- Regulatory: 4CP → 12CP overhaul mandated by SB6, target Dec 31 2026
  (PUCT 58484). For a residential fleet, coincident-peak value is
  energy/portfolio, not a transmission credit.
- The math backbone (two graphs, three regimes, separability, impact bound,
  no-universal-4/3) is in `research.tex`; notation reused throughout.
