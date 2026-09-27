"""Shared helpers for the O1-O6 simulations: paths, style, table writing."""
from __future__ import annotations

import os
import csv
import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG_DIR = os.path.join(ROOT, "results", "figures")
TAB_DIR = os.path.join(ROOT, "results", "tables")
os.makedirs(FIG_DIR, exist_ok=True)
os.makedirs(TAB_DIR, exist_ok=True)

plt.rcParams.update({
    "figure.figsize": (7.2, 4.4),
    "figure.dpi": 130,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.size": 10,
    "axes.titlesize": 11,
    "legend.frameon": False,
})

# consistent palette (colorblind-safe)
C_MAIN = "#1f77b4"
C_HARM = "#d62728"
C_SAFE = "#2ca02c"
C_WARN = "#ff7f0e"
C_MUTED = "#7f7f7f"


def savefig(fig, name: str) -> str:
    path = os.path.join(FIG_DIR, name)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def write_table(name: str, header, rows) -> str:
    path = os.path.join(TAB_DIR, name)
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return path


def annotate_defense(ax, text: str):
    """Stamp the paired mitigation on an offensive figure (SPEC acceptance)."""
    ax.text(0.98, 0.02, "DEFENSE: " + text, transform=ax.transAxes,
            ha="right", va="bottom", fontsize=8.5, color=C_SAFE,
            bbox=dict(boxstyle="round,pad=0.35", fc="#eaf7ea", ec=C_SAFE, alpha=0.9))
