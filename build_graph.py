"""
Builds a company graph from partner_map.json and founder_map.json.

Nodes: every company appearing in either map.
Node attributes: VCs, rounds, total funding (from VC txt files where available).
Edges: undirected — (u,v) exists if u partners with v OR there was founder movement between them.
Each edge stores which relationship types apply: "partner", "founder".

Output: company_graph.json
"""
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARTNER_MAP = os.path.join(SCRIPT_DIR, "partner_map.json")
FOUNDER_MAP = os.path.join(SCRIPT_DIR, "founder_map.json")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "company_graph.json")

sys.path.insert(0, SCRIPT_DIR)
from top_funded_companies import parse_file, Company


def build_company_index() -> dict[str, Company]:
    """Parse all VC txt files and return a name -> Company map."""
    companies: dict[str, Company] = {}
    txt_files = [
        os.path.join(SCRIPT_DIR, f)
        for f in os.listdir(SCRIPT_DIR)
        if f.endswith(".txt") and f != "talent_fac.txt"
    ]
    for filepath in txt_files:
        for entry in parse_file(filepath):
            name = entry["company"]
            if name not in companies:
                companies[name] = Company(name)
            companies[name].add_round(entry["round_type"], entry["amount"], entry["vc"])
    return companies


def company_node(name: str, company_index: dict[str, "Company"]) -> dict:
    """Build the node attribute dict for a company."""
    co = company_index.get(name)
    if co is None:
        return {"vcs": [], "rounds": {}, "total_funding": 0}

    rounds = {}
    for r in co.rounds:
        rounds[r.round_type] = {
            "amount": r.amount,
            "vcs": r.vcs,
        }

    all_vcs = list({vc for r in co.rounds for vc in r.vcs})

    return {
        "vcs": all_vcs,
        "rounds": rounds,
        "total_funding": co.total_funding,
    }


def main():
    with open(PARTNER_MAP) as f:
        partner_map: dict[str, list[str]] = json.load(f)
    with open(FOUNDER_MAP) as f:
        founder_map: dict[str, list[str]] = json.load(f)

    company_index = build_company_index()

    # Collect all node names
    all_names: set[str] = set()
    for src, targets in partner_map.items():
        all_names.add(src)
        all_names.update(targets)
    for src, targets in founder_map.items():
        all_names.add(src)
        all_names.update(targets)

    # Build nodes
    nodes = {name: company_node(name, company_index) for name in sorted(all_names)}

    # Build edges — keyed as adjacency dict: edges[u][v] = ["partner"?, "founder"?]
    # We store both directions so lookup is O(1) either way
    edges: dict[str, dict[str, list[str]]] = {name: {} for name in all_names}

    def add_edge(u: str, v: str, rel: str):
        if v not in edges[u]:
            edges[u][v] = []
        if rel not in edges[u][v]:
            edges[u][v].append(rel)
        if u not in edges[v]:
            edges[v][u] = []
        if rel not in edges[v][u]:
            edges[v][u].append(rel)

    for src, targets in partner_map.items():
        for tgt in targets:
            add_edge(src, tgt, "partner")

    for src, targets in founder_map.items():
        for tgt in targets:
            add_edge(src, tgt, "founder")

    graph = {"nodes": nodes, "edges": edges}

    with open(OUTPUT_FILE, "w") as f:
        json.dump(graph, f, indent=2)

    num_edges = sum(len(v) for v in edges.values()) // 2
    print(f"Graph built: {len(nodes)} nodes, {num_edges} undirected edges")
    print(f"Written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
