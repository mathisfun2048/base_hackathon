# Base to Based — Two-Graph Fleet Coordination

A math model + defensive vulnerability map for a distributed home-battery Virtual
Power Plant (~20k units, ~20 kW / 40 kWh → ~400 MW / 800 MWh). We formalize when
coordinating a fleet creates value, then flip the objective to map — and cap — how
that same leverage could be misused. Requested by the fleet owner; defensive framing
throughout, every offensive result paired with a mitigation.

## Quick start

    python -m pip install -r requirements.txt   # numpy / scipy / pandas / matplotlib
    python run_all.py                            # runs O1–O12, writes results/

Outputs land in `results/figures/*.png`, `results/tables/*.csv`, and `results/SUMMARY.md`.
Run one output on its own, e.g.:

    python -m sims.o1_feeder_threshold

Build the writeups (needs a LaTeX toolchain):

    pdflatex research.tex      # full paper (math backbone)
    pdflatex cheat_sheet.tex   # one-page consolidated summary

## Tech stack & architecture

- **Python** (numpy, scipy, pandas, matplotlib). No service or account required.
- **LinDistFlow** implemented directly on a radial tree (no solver dependency).
- Optional on Python ≤ 3.12: `gridstatus` (historical ERCOT scan), `pandapower`
  (canonical IEEE test feeders). The toolkit degrades gracefully without them.
- **LaTeX** for the paper (`research.tex`) and summary (`cheat_sheet.tex`).


Team roster (names, roles, contacts)
- Arya Chakrabarti: Math and Analysis, arya.chakrabarti@utexas.edu
- Arthur Chen: Math and Analysis, arya.chakrabarti@utexas.edu
