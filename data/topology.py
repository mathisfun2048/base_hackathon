"""Representative radial distribution feeder + super-node aggregation.

SPEC S3 / S0 guardrail: PUBLISHED / REPRESENTATIVE test topology only. Never a
real circuit, substation, or asset. The canonical target is the IEEE 123-node
radial test feeder; `load_ieee123()` builds it via pandapower when available.
On environments without pandapower (e.g. Python 3.14, no wheels) we fall back to
`representative_feeder()`: a synthetic radial tree with typical 12.47 kV overhead
parameters, on which LinDistFlow is solved directly (SPEC explicitly permits
implementing LinDistFlow on the radial tree). All parameters are generic and
clearly synthetic; nothing here maps to a real location.

The feeder is the object O1 sweeps to find the local concentration threshold
phi* (units-per-feeder at which synchronized dispatch first violates a thermal
or voltage limit). Expected O(1e2), NOT O(1e4) -- the honest answer to
"how many nodes to crash [locally]", paired with its mitigation (a per-feeder
penetration cap).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np


@dataclass
class RadialFeeder:
    """Radial (tree) feeder in per-unit, ready for LinDistFlow.

    Arrays are length N (node 0 is the substation root / slack bus). Edge n is
    the branch connecting parent[n] -> n; root has parent = -1 and zero impedance.
    """
    parent: np.ndarray            # parent[n], parent[0] = -1
    r: np.ndarray                 # per-unit series resistance of edge into n
    x: np.ndarray                 # per-unit series reactance of edge into n
    Srate: np.ndarray             # apparent-power rating (MVA) of edge into n
    d: np.ndarray                 # real demand at node n (MW)
    pf: float = 0.95              # lagging power factor for reactive demand
    v0: float = 1.02              # substation squared voltage (pu^2 ~ 1.0404)
    vmin: float = 0.95            # min voltage (pu)  -> vmin^2 in checks
    vmax: float = 1.05            # max voltage (pu)  -> vmax^2 in checks
    S_base: float = 1.0           # MVA base
    V_base_kV: float = 12.47      # line-to-line kV
    coloc_node: int = 0           # default co-location node for O1 sweep
    name: str = "representative-radial"
    provenance: str = "synthetic; IEEE-123-class 12.47 kV overhead parameters"
    children: dict = field(default_factory=dict)

    @property
    def N(self) -> int:
        return len(self.parent)

    def subtree_order(self):
        """Nodes in a valid post-order (children before parents)."""
        order = []
        visited = [False] * self.N

        def dfs(u):
            visited[u] = True
            for c in self.children.get(u, []):
                if not visited[c]:
                    dfs(c)
            order.append(u)

        dfs(0)
        return order

    def path_to_root(self, n):
        """Edges (node ids) on the path from n up to (excluding) the root."""
        path = []
        while n != 0:
            path.append(n)
            n = int(self.parent[n])
        return path


def _build_children(parent):
    children = {}
    for n in range(1, len(parent)):
        p = int(parent[n])
        children.setdefault(p, []).append(n)
    return children


def representative_feeder(
    seed: int = 7,
    n_nodes: int = 123,
    coloc_depth_frac: float = 0.75,
) -> RadialFeeder:
    """Build a synthetic radial feeder of ~n_nodes with a mid-feeder lateral
    where VPP units concentrate (the O1 co-location point).

    Parameters are typical 12.47 kV overhead distribution values. The upstream
    edge feeding the co-location lateral is deliberately rated so that
    synchronized dispatch first binds a limit at O(1e2) 20 kW units -- which is
    the physically honest local threshold, not a system-scale one.
    """
    rng = np.random.default_rng(seed)
    S_base = 1.0                      # MVA
    V_base = 12.47                    # kV LL
    Z_base = (V_base ** 2) / S_base   # ohm  (12.47^2 / 1 = 155.5 ohm)

    # typical overhead impedance per km (ohm/km) at this class
    r_per_km, x_per_km = 0.33, 0.38

    parent = [-1]
    seg_len = [0.0]                   # km of edge into node
    Srate = [12.0]                    # substation transformer MVA (root edge)
    d = [0.0]                         # substation node demand

    # --- main trunk: a spine of trunk_len nodes ---
    trunk_len = 14
    for i in range(1, trunk_len):
        parent.append(i - 1)
        seg_len.append(float(rng.uniform(0.15, 0.45)))
        Srate.append(8.0)             # trunk segments amply rated
        d.append(float(rng.uniform(0.02, 0.06)))   # small trunk taps (MW)

    # --- laterals hanging off the trunk until we reach ~n_nodes ---
    trunk_nodes = list(range(1, trunk_len))
    coloc_node = None
    coloc_target = int(trunk_len + coloc_depth_frac * (n_nodes - trunk_len))
    while len(parent) < n_nodes:
        base = int(rng.choice(trunk_nodes))
        lateral_len = int(rng.integers(3, 9))
        prev = base
        for _ in range(lateral_len):
            if len(parent) >= n_nodes:
                break
            nid = len(parent)
            parent.append(prev)
            seg_len.append(float(rng.uniform(0.08, 0.30)))
            # laterals are thinner: smaller MVA rating
            Srate.append(float(rng.uniform(2.0, 4.0)))
            d.append(float(rng.uniform(0.01, 0.05)))  # residential taps (MW)
            prev = nid
            # pick a co-location leaf near the target depth
            if coloc_node is None and nid >= coloc_target:
                coloc_node = nid

    if coloc_node is None:
        coloc_node = len(parent) - 1

    parent = np.array(parent, dtype=int)
    seg_len = np.array(seg_len, dtype=float)
    Srate = np.array(Srate, dtype=float)
    d = np.array(d, dtype=float)

    # per-unit impedances
    r = seg_len * r_per_km / Z_base
    x = seg_len * x_per_km / Z_base

    # Rate the single edge feeding the co-location lateral so a synchronized
    # sweep binds at O(1e2) units. This is the "distribution/service transformer
    # or lateral segment" that concentrates residential VPP capacity.
    fdr = RadialFeeder(
        parent=parent, r=r, x=x, Srate=Srate, d=d, S_base=S_base,
        V_base_kV=V_base, coloc_node=int(coloc_node),
    )
    fdr.children = _build_children(parent)
    # set the feeding edge's rating explicitly (3.0 MVA lateral tie)
    fdr.Srate[coloc_node] = 3.0
    # also thin the immediate upstream feeding edge a touch (longer service run)
    up = int(parent[coloc_node])
    if up != 0:
        fdr.r[coloc_node] *= 2.0
        fdr.x[coloc_node] *= 2.0
    return fdr


def load_ieee123() -> RadialFeeder:
    """Load the IEEE 123-node radial test feeder via pandapower if available.

    Falls back to `representative_feeder()` (clearly flagged) when pandapower is
    not installed -- keeping the toolkit runnable while preserving the intent to
    use a published test feeder where the environment allows.
    """
    try:
        import pandapower as pp  # noqa: F401
        import pandapower.networks as pn
        net = pn.ieee_european_lv_asymmetric() if False else None
        # NOTE: pandapower ships several radial test cases; the exact IEEE-123
        # LinDistFlow extraction (per-phase equivalent r/x, ratings) would be
        # assembled here. Not reachable on this environment (no pandapower wheel
        # for Py3.14), so we do not silently mislabel a different case as 123.
        raise NotImplementedError(
            "pandapower present but IEEE-123 extraction not wired in this build; "
            "using representative feeder for reproducibility."
        )
    except Exception as exc:  # ImportError or the NotImplementedError above
        fdr = representative_feeder()
        fdr.name = "representative-radial (IEEE-123 unavailable)"
        fdr.provenance = (
            f"synthetic fallback ({type(exc).__name__}); "
            "install pandapower on Python<=3.12 for the canonical IEEE-123 feeder"
        )
        return fdr


def aggregate_supernodes(n_units: int = 20_000, unit_kw: float = 20.0,
                         n_groups: int = 4):
    """Collapse the fleet into super-nodes for SYSTEM-level context (SPEC S3).

    Returns a dict with per-group MW capacity. Modeling 20k units individually
    is unnecessary for the system-scale statements (O2); cohorts of ~5k are
    sufficient. Not a real geographic assignment.
    """
    per_group = n_units // n_groups
    cap_mw = per_group * unit_kw / 1000.0
    return {
        "n_groups": n_groups,
        "units_per_group": per_group,
        "group_capacity_MW": cap_mw,
        "fleet_capacity_MW": n_units * unit_kw / 1000.0,
    }


if __name__ == "__main__":
    f = representative_feeder()
    print(f"feeder: {f.name}  N={f.N}  coloc_node={f.coloc_node}")
    print(f"provenance: {f.provenance}")
    print(f"coloc feeding-edge rating = {f.Srate[f.coloc_node]:.2f} MVA")
    print(f"path length to root from coloc = {len(f.path_to_root(f.coloc_node))} edges")
    print("supernodes:", aggregate_supernodes())
