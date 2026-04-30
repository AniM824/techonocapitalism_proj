"""
Graph analyses on the VC investment ecosystem.

1. Connected component analysis per VC portfolio subgraph
2. Triangle detection (VC invests in A & B, A-B are partners)
3. VC co-investment network
4. Talent pipeline analysis (do founder prior employers land in same VC portfolios?)

Statistical tests where applicable.
"""
import json
import os
import sys
import random
from collections import defaultdict
from itertools import combinations
from scipy.stats import mannwhitneyu, hypergeom

import networkx as nx
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from top_funded_companies import parse_file, Company

GRAPH_FILE   = os.path.join(SCRIPT_DIR, "company_graph.json")
FOUNDER_FILE = os.path.join(SCRIPT_DIR, "founder_map.json")
RESULTS_FILE = os.path.join(SCRIPT_DIR, "analysis_results.json")

PERMUTATION_N = 1000   # iterations for permutation tests
RANDOM_SEED   = 42


# ── helpers ──────────────────────────────────────────────────────────────────

def load_graph() -> tuple[nx.Graph, dict]:
    with open(GRAPH_FILE) as f:
        raw = json.load(f)
    G = nx.Graph()
    for node, attrs in raw["nodes"].items():
        G.add_node(node, **attrs)
    for u, neighbors in raw["edges"].items():
        for v, rels in neighbors.items():
            if not G.has_edge(u, v):
                G.add_edge(u, v, types=rels)
    return G, raw


def build_vc_portfolios(G: nx.Graph) -> dict[str, set[str]]:
    """Map each VC name → set of companies they invested in (present in graph)."""
    portfolios: dict[str, set[str]] = defaultdict(set)
    for node, data in G.nodes(data=True):
        for vc in data.get("vcs", []):
            portfolios[vc].add(node)
    return dict(portfolios)


def partner_edges(G: nx.Graph) -> list[tuple[str, str]]:
    return [(u, v) for u, v, d in G.edges(data=True) if "partner" in d.get("types", [])]


def header(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


# ── 1. Connected Components per VC portfolio ──────────────────────────────────

def analyze_components(G: nx.Graph, portfolios: dict[str, set[str]]):
    header("1. CONNECTED COMPONENT ANALYSIS PER VC")

    results = {}
    detail  = {}
    for vc, companies in portfolios.items():
        sub   = G.subgraph(companies)
        comps = sorted(nx.connected_components(sub), key=len, reverse=True)
        sizes = [len(c) for c in comps]
        results[vc] = sizes
        detail[vc]  = {
            "portfolio_size": sum(sizes),
            "num_components": len(sizes),
            "largest_cc_size": sizes[0],
            "isolated_count": sizes.count(1),
            "components": [sorted(c) for c in comps],   # full company lists
        }

    print(f"\n{'VC':<15} {'Portfolio':>9} {'Components':>10} {'Largest CC':>10} {'Isolated':>8}")
    print("-" * 58)
    for vc, sizes in sorted(results.items(), key=lambda x: -x[1][0]):
        d = detail[vc]
        print(f"{vc:<15} {d['portfolio_size']:>9} {d['num_components']:>10} {d['largest_cc_size']:>10} {d['isolated_count']:>8}")

    by_size = sorted(results.items(), key=lambda x: -sum(x[1]))
    top_vcs    = [v for v, _ in by_size[:4]]
    bottom_vcs = [v for v, _ in by_size[-4:]]
    stat, p = mannwhitneyu(
        [results[v][0] for v in top_vcs],
        [results[v][0] for v in bottom_vcs],
        alternative="greater"
    )
    print(f"\n  Mann-Whitney U (top-4 vs bottom-4 VCs, largest CC size):")
    print(f"  stat={stat:.1f}, p={p:.4f} — {'significant' if p < 0.05 else 'not significant'} at α=0.05")

    return results, detail


# ── 2. Triangle Detection ─────────────────────────────────────────────────────

def get_vc_triangle_pairs(G: nx.Graph, portfolios: dict[str, set[str]]) -> dict[str, list]:
    """For each VC, return all (A, B) portfolio pairs connected by a partner edge."""
    result = {}
    for vc, companies in portfolios.items():
        pairs = []
        cos = list(companies)
        for i in range(len(cos)):
            for j in range(i + 1, len(cos)):
                if G.has_edge(cos[i], cos[j]) and "partner" in G[cos[i]][cos[j]].get("types", []):
                    pairs.append([cos[i], cos[j]])
        result[vc] = pairs
    return result


def analyze_triangles(G: nx.Graph, portfolios: dict[str, set[str]]):
    header("2. TRIANGLE DETECTION (VC invests in A & B, A—B are partners)")

    vc_pairs = get_vc_triangle_pairs(G, portfolios)
    observed = {vc: len(pairs) for vc, pairs in vc_pairs.items()}

    rng = random.Random(RANDOM_SEED)
    all_nodes = list(G.nodes())
    p_edges   = partner_edges(G)
    null_counts: dict[str, list[int]] = {vc: [] for vc in portfolios}

    for _ in range(PERMUTATION_N):
        rewired = set()
        while len(rewired) < len(p_edges):
            u, v = rng.sample(all_nodes, 2)
            if u != v:
                rewired.add((min(u, v), max(u, v)))
        G_null = nx.Graph(list(rewired))
        G_null.add_nodes_from(all_nodes)
        for vc, companies in portfolios.items():
            null_counts[vc].append(sum(1 for a, b in combinations(companies, 2) if G_null.has_edge(a, b)))

    detail = {}
    print(f"\n{'VC':<15} {'Triangles':>9} {'Null mean':>10} {'Null std':>9} {'p-value':>9} {'Sig':>4}")
    print("-" * 62)
    for vc, obs in sorted(observed.items(), key=lambda x: -x[1]):
        null      = null_counts[vc]
        null_mean = np.mean(null)
        null_std  = np.std(null)
        p         = float(np.mean([n >= obs for n in null]))
        sig       = "*" if p < 0.05 else ""
        print(f"{vc:<15} {obs:>9} {null_mean:>10.2f} {null_std:>9.2f} {p:>9.4f} {sig:>4}")
        detail[vc] = {
            "count": obs,
            "null_mean": round(null_mean, 3),
            "null_std": round(null_std, 3),
            "p_value": round(p, 4),
            "significant": p < 0.05,
            "pairs": vc_pairs[vc],
        }

    print("\n  * p < 0.05 (permutation test, one-tailed)")
    return observed, detail


# ── 3. VC Co-investment Network ───────────────────────────────────────────────

def analyze_coinvestment(portfolios: dict[str, set[str]]):
    header("3. VC CO-INVESTMENT NETWORK")

    vcs   = list(portfolios.keys())
    pairs = []
    for i in range(len(vcs)):
        for j in range(i + 1, len(vcs)):
            a, b   = vcs[i], vcs[j]
            shared = portfolios[a] & portfolios[b]
            if shared:
                jaccard = len(shared) / len(portfolios[a] | portfolios[b])
                pairs.append((a, b, len(shared), jaccard, sorted(shared)))

    pairs.sort(key=lambda x: -x[2])

    print(f"\n{'VC A':<15} {'VC B':<15} {'Shared':>6} {'Jaccard':>9}")
    print("-" * 50)
    for a, b, n, j, _ in pairs:
        print(f"{a:<15} {b:<15} {n:>6} {j:>9.3f}")

    G_vc = nx.Graph()
    for a, b, n, j, companies in pairs:
        G_vc.add_edge(a, b, weight=n, jaccard=j)

    degree_w = dict(nx.degree(G_vc, weight="weight"))
    print("\n  Weighted degree (total shared companies with all other VCs):")
    for vc, deg in sorted(degree_w.items(), key=lambda x: -x[1]):
        print(f"    {vc:<15} {deg}")

    detail = {
        "pairs": [
            {"vc_a": a, "vc_b": b, "shared_count": n, "jaccard": round(j, 4), "companies": cos}
            for a, b, n, j, cos in pairs
        ],
        "weighted_degree": {vc: int(deg) for vc, deg in sorted(degree_w.items(), key=lambda x: -x[1])},
    }
    return G_vc, detail


# ── 4. Talent Pipeline Analysis ───────────────────────────────────────────────

def analyze_talent_pipeline(G: nx.Graph, portfolios: dict[str, set[str]]):
    header("4. TALENT PIPELINE — do VC founders come from same VC's portfolio?")

    with open(FOUNDER_FILE) as f:
        founder_map: dict[str, list[str]] = json.load(f)

    all_companies = set(G.nodes())

    print(f"\n{'VC':<15} {'Portfolio':>9} {'Founder links':>13} {'Internal':>9} {'Rate':>7} {'p-value':>9} {'Sig':>4}")
    print("-" * 72)

    detail = {}
    for vc, portfolio in sorted(portfolios.items()):
        total_links = 0
        internal    = 0
        flows       = []

        for company in portfolio:
            for emp in founder_map.get(company, []):
                if emp in all_companies:
                    total_links += 1
                    is_internal = emp in portfolio
                    if is_internal:
                        internal += 1
                    flows.append({"startup": company, "prior_employer": emp, "internal": is_internal})

        if total_links == 0:
            print(f"{vc:<15} {len(portfolio):>9} {'—':>13} {'—':>9} {'—':>7} {'—':>9}")
            detail[vc] = {"portfolio_size": len(portfolio), "total_links": 0, "flows": []}
            continue

        rate = internal / total_links
        M    = len(all_companies)
        p    = float(hypergeom.sf(internal - 1, M, len(portfolio), total_links))
        sig  = "*" if p < 0.05 else ""
        print(f"{vc:<15} {len(portfolio):>9} {total_links:>13} {internal:>9} {rate:>7.3f} {p:>9.4f} {sig:>4}")
        detail[vc] = {
            "portfolio_size": len(portfolio),
            "total_links": total_links,
            "internal": internal,
            "rate": round(rate, 4),
            "p_value": round(p, 4),
            "significant": p < 0.05,
            "flows": flows,
        }

    print("\n  * p < 0.05 (hypergeometric test — internal founder rate above chance)")
    return detail


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    G, raw = load_graph()
    portfolios = build_vc_portfolios(G)

    print(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    print(f"VCs: {list(portfolios.keys())}")

    _, comp_detail      = analyze_components(G, portfolios)
    _, tri_detail       = analyze_triangles(G, portfolios)
    _, coinv_detail     = analyze_coinvestment(portfolios)
    talent_detail       = analyze_talent_pipeline(G, portfolios)

    results = {
        "components":      comp_detail,
        "triangles":       tri_detail,
        "coinvestment":    coinv_detail,
        "talent_pipeline": talent_detail,
    }
    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull detail written to {RESULTS_FILE}")


if __name__ == "__main__":
    main()
