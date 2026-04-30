"""
Tests whether companies sharing a sector are more likely to have an edge
in the ecosystem graph.

Method: 2x2 Fisher's exact test on all unordered company pairs.
  Rows: shares_sector (yes/no)
  Cols: has_edge      (yes/no)

Also runs a permutation test (sector labels shuffled) to validate,
since pair observations are not strictly independent.
"""
import json
import os
import random
from itertools import combinations

try:
    from scipy.stats import fisher_exact
except ImportError:
    fisher_exact = None

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── load graph ────────────────────────────────────────────────────────────────
with open(os.path.join(SCRIPT_DIR, "company_graph.json")) as f:
    g = json.load(f)

nodes = list(g["nodes"].keys())
edges_raw = g["edges"]

edge_set: set[tuple[str, str]] = set()
for u, nbrs in edges_raw.items():
    for v in nbrs:
        a, b = (u, v) if u < v else (v, u)
        edge_set.add((a, b))

# ── load sector maps ──────────────────────────────────────────────────────────
sector_map: dict[str, list[str]] = {}
for fname in ["sector_map.json", "talent_fac_sector_map.json", "unlabelled_sector_map.json"]:
    fpath = os.path.join(SCRIPT_DIR, fname)
    if os.path.exists(fpath):
        with open(fpath) as f:
            sector_map.update(json.load(f))

node_sectors: dict[str, set[str]] = {
    n: set(sector_map.get(n, [])) for n in nodes
}

labelled_nodes = [n for n in nodes if node_sectors[n]]
print(f"Graph: {len(nodes)} nodes, {len(edge_set)} undirected edges")
print(f"Labelled nodes (have ≥1 sector): {len(labelled_nodes)}")
print(f"Pairs to evaluate: {len(labelled_nodes)*(len(labelled_nodes)-1)//2:,}\n")


# ── build contingency table ───────────────────────────────────────────────────
def contingency(node_list: list[str], sectors: dict[str, set[str]]) -> tuple[int,int,int,int]:
    """Returns (same_edge, same_noedge, diff_edge, diff_noedge)."""
    same_edge = same_noedge = diff_edge = diff_noedge = 0
    for u, v in combinations(node_list, 2):
        a, b = (u, v) if u < v else (v, u)
        has_edge   = (a, b) in edge_set
        same_sector = bool(sectors[u] & sectors[v])
        if same_sector:
            if has_edge: same_edge   += 1
            else:        same_noedge += 1
        else:
            if has_edge: diff_edge   += 1
            else:        diff_noedge += 1
    return same_edge, same_noedge, diff_edge, diff_noedge


same_edge, same_noedge, diff_edge, diff_noedge = contingency(labelled_nodes, node_sectors)

total_pairs  = same_edge + same_noedge + diff_edge + diff_noedge
same_pairs   = same_edge + same_noedge
diff_pairs   = diff_edge + diff_noedge
edge_pairs   = same_edge + diff_edge

p_edge_given_same = same_edge / same_pairs if same_pairs else 0
p_edge_given_diff = diff_edge / diff_pairs if diff_pairs else 0
odds_ratio = (same_edge * diff_noedge) / (same_noedge * diff_edge) if (same_noedge * diff_edge) else float("inf")

print("── Contingency table ────────────────────────────────")
print(f"{'':25s} {'edge':>10s} {'no edge':>12s} {'total':>10s}")
print(f"{'shares sector':25s} {same_edge:>10,} {same_noedge:>12,} {same_pairs:>10,}")
print(f"{'different sector':25s} {diff_edge:>10,} {diff_noedge:>12,} {diff_pairs:>10,}")
print(f"{'total':25s} {edge_pairs:>10,} {(same_noedge+diff_noedge):>12,} {total_pairs:>10,}")
print()
print(f"P(edge | same sector)  = {p_edge_given_same:.4%}")
print(f"P(edge | diff sector)  = {p_edge_given_diff:.4%}")
print(f"Odds ratio             = {odds_ratio:.3f}x")
print()

# ── Fisher's exact test ───────────────────────────────────────────────────────
if fisher_exact:
    table = [[same_edge, same_noedge], [diff_edge, diff_noedge]]
    oddsratio_scipy, p_value = fisher_exact(table, alternative="greater")
    print("── Fisher's exact test (H₁: same-sector pairs more likely to be connected) ──")
    print(f"p-value    = {p_value:.2e}")
    print(f"Odds ratio = {oddsratio_scipy:.3f}")
    print()
else:
    print("scipy not available — skipping Fisher's exact test")
    print()

# ── Permutation test ──────────────────────────────────────────────────────────
# Shuffle sector labels across nodes; count same-sector edges each time.
# This accounts for the non-independence of pairs sharing a node.
N_PERM = 5_000
random.seed(42)

sector_values = [node_sectors[n] for n in labelled_nodes]
observed_same_edge = same_edge

count_ge = 0
for _ in range(N_PERM):
    shuffled = dict(zip(labelled_nodes, random.sample(sector_values, len(sector_values))))
    perm_same_edge = sum(
        1 for u, v in edge_set
        if u in shuffled and v in shuffled and (shuffled[u] & shuffled[v])
    )
    if perm_same_edge >= observed_same_edge:
        count_ge += 1

perm_p = count_ge / N_PERM

print("── Permutation test (5,000 shuffles of sector labels) ───────────────────")
print(f"Observed same-sector edges : {observed_same_edge}")
print(f"Permutation p-value        : {perm_p:.4f}  ({count_ge}/{N_PERM} shuffles ≥ observed)")
print()

# ── Per-sector breakdown ──────────────────────────────────────────────────────
print("── Per-sector edge enrichment ───────────────────────────────────────────")
print(f"{'Sector':30s} {'n_companies':>11s} {'intra_edges':>11s} {'P(edge|same)':>13s} {'P(edge|diff)':>13s} {'ratio':>7s}")
all_sectors = sorted({s for sset in node_sectors.values() for s in sset})
for sector in all_sectors:
    in_sector  = [n for n in labelled_nodes if sector in node_sectors[n]]
    out_sector = [n for n in labelled_nodes if sector not in node_sectors[n]]
    if len(in_sector) < 2:
        continue
    intra_e = sum(
        1 for u, v in combinations(in_sector, 2)
        if ((u,v) if u<v else (v,u)) in edge_set
    )
    intra_n = len(in_sector)*(len(in_sector)-1)//2
    cross_e = sum(
        1 for u in in_sector for v in out_sector
        if ((u,v) if u<v else (v,u)) in edge_set
    )
    cross_n = len(in_sector)*len(out_sector)
    p_in  = intra_e / intra_n if intra_n else 0
    p_out = cross_e / cross_n if cross_n else 0
    ratio = p_in / p_out if p_out else float("inf")
    print(f"{sector:30s} {len(in_sector):>11} {intra_e:>11} {p_in:>13.4%} {p_out:>13.4%} {ratio:>7.2f}x")
