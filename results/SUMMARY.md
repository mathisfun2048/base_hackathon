# VPP Red-Team / Vulnerability Analysis -- Results Summary

Defensive vulnerability map of a distributed battery VPP (~20k units, ~20 kW/40 kWh -> ~400 MW/800 MWh), requested by the fleet owner. Deliverable: thresholds, sensitivities, detection signatures, and mitigations -- not an attack tool. Every offensive result is paired with its defense. Topology is synthetic/representative; eps is a generic anomaly budget.

**Price data:** calm interval is REAL ERCOT (REAL ERCOT RTM 15-min SPP dashboard, Load Zone lzNorth, 2026-09-26 (pulled 2026-09-26 21:02:00-0500); https://www.ercot.com/api/1/services/read/dashboards/systemWidePrices.json); scarcity anchor is the ERCOT offer-cap scarcity reference (beta from the structural inverse-supply curve), labeled on every figure.

## Punchline
There is no "crash ERCOT" number: 400 MW is ~0.4% of an ~85-95 GW peak and the 2-hour energy budget forbids sustained action. The real threat is LOCAL (feeder concentration) and amplification of already-stressed intervals -- both bounded by caps and revealed by a correlation signature.

## O1
O1: On the representative radial feeder, 108 synchronized 20 kW units (2.2 MW) at one concentration node first violate a thermal limit -- O(1e2), not O(1e4). The local threat is feeder concentration, and it is capped by a per-feeder penetration limit (~75 units) plus a synchronized-dispatch interlock at the concentration node.

- figure: `results/figures/O1_feeder_threshold.png`
- table: `results/tables/O1_feeder_threshold.csv`

## O11
O11 (topology sensitivity): Sweeping representative feeder archetypes, the local concentration threshold ranges from ~47 units (dense urban (short lines, pad xfmr)) to ~142 units (suburban (medium lateral)) on one shared transformer -- always O(1e2), never the ~20k fleet, so the physical danger is LOCAL concentration in EVERY topology. But the binding mode differs: dense-urban blocks overheat their wires (thermal), while long rural lines break on VOLTAGE/flicker first -- so a single global per-feeder cap is wrong; it must be set per archetype below that feeder's own phi*. And the coordinated-vs-independent panel shows the shared limit only ever binds under lockstep (independent dispatch of the same units never overloads it) -- so capping cross-unit correlation (O6) removes the mechanism everywhere. [all feeders synthetic/representative; no real asset]

- figure: `results/figures/O11_topology_sensitivity.png`
- table: `results/tables/O11_topology_sensitivity.csv`

## O2
O2: Local price sensitivity is ~3142x larger in scarcity (beta=7.86e-01) than in calm (beta=2.50e-04) ($/MWh per MW). Even at scarcity the full 400 MW fleet moves price by at most ~314 $/MWh (12.6% of the $2500 level), and in calm hours by 0.10 $/MWh (0.44%). NO SYSTEM CRASH: 400 MW is 0.44% of a ~90 GW peak and the 800 MWh budget forbids sustained action beyond ~2 h. Leverage is structural, offer-cap bounded, and energy-limited; the real risk is LOCAL (O1) and amplification of already-stressed intervals, not system collapse. [calm: REAL ERCOT 2026-09-26 Load Zone; scarcity: offer-cap reference]

- figure: `results/figures/O2_price_sensitivity.png`
- table: `results/tables/O2_price_sensitivity.csv`

## O10
O10 (market-making at scale is the harm): The three dispatch regimes in research.tex differ only by the price each internalizes; the strategic fleet withholds (p + Q*p') to hold price up -- that is market power. Priced out on a real-structure ERCOT scarcity interval (~$2,500/MWh, implied load ~83 GW settling at the single clearing price), a hostile/compromised 240k-unit fleet (4,800 MW) inflates what ALL Texas load pays in ONE 2-hour window by ~$772M -- about $77/household/event (~$386/household over a 5-event summer). Today's 20k fleet moves it far less (~$103.8M), so the harm is a consequence of SCALE: at 3x/yr growth the fleet crosses into systemic territory within ~2 years. And it is negative-sum -- for every $1 the owner earns by withholding, ratepayers pay ~$61, because the price is set at the margin but paid on all load. Private gain != social good. DEFENSE: a per-scarcity fleet-share screen, the cross-unit correlation detector (O6), and a no-coordinated-withhold rule under low reserve (O7). [price STRUCTURE: ERCOT offer-cap scarcity reference, labeled]

- figure: `results/figures/O10_market_power.png`
- table: `results/tables/O10_market_power.csv`

## O7
O7 (nodes to crash the system): Defining a crash as EEA3 rolling blackouts (PRC<=1,430 MW), the number of coordinated 20 kW nodes required depends on the starting reserve. On today's REAL grid (min PRC 9,231 MW) it takes ~195,025 nodes -- ~10x the entire 20,000-unit fleet -- so the fleet CANNOT crash a healthy system. But on an already-critical grid at EEA2 (1,750 MW, as on 2023-09-06), only ~8,000 nodes (40% of the fleet) are enough to tip into rolling blackouts; during Winter Storm Uri the grid was already in EEA3. The fleet becomes a marginal trigger only when reserves are already below ~2,230 MW (~EEA1). Market 'crash' is bounded too: scarcity pricing pins the price at the $5,000 cap on its own, and the fleet's own price impact is limited (O2). Real threat = amplification of already-stressed intervals. DEFENSE: forbid coordinated charging during EEA/low-PRC, plus per-feeder caps (O1) and the correlation detector (O6).

- figure: `results/figures/O7_system_crash.png`
- table: `results/tables/O7_system_crash.csv`

## O3
O3: The coordination premium is ~1 (separable) below phi*~108, then rises steeply -- coordinated synchronization produces feeder harm that diversified dispatch of the same units does not, because the shared thermal limit only binds under synchronization. This mirrors the owner-side premium rho. The premium exists ONLY above threshold, so the per-feeder cap (O1) and the correlation detector (O6) remove it.

- figure: `results/figures/O3_coordination_premium.png`
- table: `results/tables/O3_coordination_premium.csv`

## O4
O4: Harm rises monotonically with the stealth budget eps, but so does the probability the correlation+bias detector fires. Detection becomes near-certain (>=90%) at eps*=0.25 per-unit deviation, which caps stealthy cost inflation at ~$13.5M over a 2-hour stressed window. The mitigation set-point is therefore a per-unit telemetry-deviation alarm at eps*=0.25 [scarcity anchor: ERCOT offer-cap reference].

- figure: `results/figures/O4_stealth_frontier.png`
- table: `results/tables/O4_stealth_frontier.csv`

## O9
O9 (subtle inefficiency over time): A persistent sub-threshold deviation inflates cost and erodes efficiency a little each day -- invisible to per-interval checks. Left unmonitored over 180 days it compounds. But a sequential CUSUM detector on the persistent directional bias fires even for tiny stealth levels, and because a stealthier attack has proportionally smaller daily harm yet takes proportionally longer to detect, the cumulative harm before detection is BOUNDED at ~$6.8M regardless of how slow the attacker goes. DEFENSE: cumulative/sequential monitoring (CUSUM on bias + long-window correlation) on top of the per-interval budgets -- this bound is the monitoring set-point.

- figure: `results/figures/O9_slow_inefficiency.png`
- table: `results/tables/O9_slow_inefficiency.csv`

## O5
O5: A compromised controller operating within the stealth budget can accelerate fleet aging up to ~7.4x benign at eps=1, but the telemetry signature -- elevated equivalent-full-cycles/day, a persistent wrong-way directional bias, DoD-floor breaches, and cross-unit correlation -- makes detection near-certain by eps*=0.25, capping stealthy acceleration at ~1.74x. Firmware/operational bounds (C-rate<=0.5, 10% DoD floor, <=2 EFC/day, >=5 min dwell, ramp limit) cap the residual. No destruction-optimal schedule is produced. [price shape: ERCOT offer-cap scarcity reference]

- figure: `results/figures/O5_degradation.png`
- table: `results/tables/O5_degradation.csv`

## O8
O8 (inverter-switching hardware attack): Benign dispatch reverses ~6 times/day (inverter life >100 yr). Constant 1 Hz switching (86,400 reversals/day) consumes IGBT power-cycling life in ~6 days and battery life in months -- a genuine hardware-destruction vector. A 5-minute minimum-dwell rule alone still permits 288 reversals/day (inverter life only ~5.3 yr), so it is NOT sufficient; the effective mitigation is a switching-COUNT budget of <= 48 reversals/day (inverter life ~32 yr) plus a ramp-rate limit. The attack is trivially detectable: reversals/day and the dwell-time distribution depart sharply from the price-optimal baseline. DEFENSE: firmware switching-count cap + min-dwell + ramp limit, with a telemetry alarm on switching frequency.

- figure: `results/figures/O8_inverter_switching.png`
- table: `results/tables/O8_inverter_switching.csv`

## O6
O6: The monitorable defense is a cross-unit correlation + directional-bias statistic (alarm at correlation>0.2, bias>0.1; standing monitor window 96 intervals ~ 1 day), a per-feeder penetration cap (~75 units), and firmware bounds (C-rate<=0.5, 10% DoD floor, <=2 EFC/day, >=5 min dwell). The ROC shown is a CONSERVATIVE case -- a ~20-unit feeder cohort over just the 2-hour attack window -- yet detection is near-certain by eps*=0.25 (a day-long, fleet-wide monitor is strictly more powerful). Together these map the generic budget to eps*<0.25, capping both cost inflation and aging acceleration below the detection threshold.

- figure: `results/figures/O6_detection_mitigation.png`
- table: `results/tables/O6_detection_mitigation.csv`
