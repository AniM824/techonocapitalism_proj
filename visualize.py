"""
Visualizations for the VC ecosystem graph.

Outputs:
  ecosystem.html       — interactive company graph (pyvis, open in browser)
  coinvestment.html    — interactive VC co-investment graph (pyvis)
  company_graph.gexf   — full graph export for Gephi
  coinvestment_heatmap.png — VC co-investment heatmap (matplotlib)
  degree_distribution.png  — node degree histogram (matplotlib)
"""
import json
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import networkx as nx
import numpy as np
from pyvis.network import Network

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

GRAPH_FILE   = os.path.join(SCRIPT_DIR, "company_graph.json")
RESULTS_FILE = os.path.join(SCRIPT_DIR, "analysis_results.json")

# ── VC colour palette ─────────────────────────────────────────────────────────
VC_COLORS = {
    "a16z":       "#1f77b4",
    "sequoia":    "#d62728",
    "lightspeed": "#ff7f0e",
    "gc":         "#2ca02c",
    "accel":      "#9467bd",
    "ff":         "#8c564b",
    "lux":        "#e377c2",
    "8vc":        "#7f7f7f",
    "kp":         "#bcbd22",
}
MULTI_VC_COLOR  = "#17becf"
NO_VC_COLOR     = "#d3d3d3"

SECTOR_COLORS = {
    "AI / Foundation Models": "#6366f1",
    "AI Applications":        "#a78bfa",
    "Defense / Dual-Use":     "#ef4444",
    "Fintech":                "#10b981",
    "Data / Dev Infra":       "#f59e0b",
    "Biotech / Life Sciences":"#ec4899",
    "Robotics / Autonomy":    "#06b6d4",
    "Energy / Climate":       "#84cc16",
    "Healthcare":             "#fb923c",
    "Space":                  "#94a3b8",
}
MIN_NODE_SIZE   = 8
MAX_NODE_SIZE   = 50


# ── helpers ───────────────────────────────────────────────────────────────────

def load_graph() -> nx.Graph:
    with open(GRAPH_FILE) as f:
        raw = json.load(f)
    G = nx.Graph()
    for node, attrs in raw["nodes"].items():
        G.add_node(node, **attrs)
    for u, neighbors in raw["edges"].items():
        for v, rels in neighbors.items():
            if not G.has_edge(u, v):
                G.add_edge(u, v, types=rels)
    return G


def node_color(vcs: list[str]) -> str:
    if not vcs:
        return NO_VC_COLOR
    known = [v for v in vcs if v in VC_COLORS]
    if len(known) == 1:
        return VC_COLORS[known[0]]
    if len(known) > 1:
        return MULTI_VC_COLOR
    return NO_VC_COLOR


def node_size(total_funding: float, min_f: float, max_f: float) -> float:
    if max_f == min_f:
        return (MIN_NODE_SIZE + MAX_NODE_SIZE) / 2
    log_f   = math.log1p(total_funding)
    log_min = math.log1p(min_f)
    log_max = math.log1p(max_f)
    t = (log_f - log_min) / (log_max - log_min)
    return MIN_NODE_SIZE + t * (MAX_NODE_SIZE - MIN_NODE_SIZE)


def fmt_funding(val: float) -> str:
    if val >= 1e9:
        return f"${val/1e9:.1f}B"
    if val >= 1e6:
        return f"${val/1e6:.1f}M"
    return f"${val:,.0f}"


# ── 1. Interactive company ecosystem graph ────────────────────────────────────

def make_ecosystem_html(G: nx.Graph):
    fundings = [d.get("total_funding", 0) for _, d in G.nodes(data=True)]
    min_f, max_f = min(fundings), max(fundings)

    # Load sector maps (portfolio companies + talent_fac companies)
    sector_map: dict[str, list[str]] = {}
    for fname in ["sector_map.json", "talent_fac_sector_map.json", "unlabelled_sector_map.json"]:
        fpath = os.path.join(SCRIPT_DIR, fname)
        if os.path.exists(fpath):
            with open(fpath) as f:
                sector_map.update(json.load(f))

    # Build node/edge dicts for vis.js
    nodes_data = []
    for node, data in G.nodes(data=True):
        vcs     = data.get("vcs", [])
        funding = data.get("total_funding", 0)
        rounds  = ", ".join(data.get("rounds", {}).keys()) or "—"
        sectors = sector_map.get(node, [])
        color   = node_color(vcs)
        size    = node_size(funding, min_f, max_f)
        tooltip = (
            f"<b>{node}</b><br>"
            f"Funding: {fmt_funding(funding)}<br>"
            f"VCs: {', '.join(vcs) or '—'}<br>"
            f"Sectors: {', '.join(sectors) or '—'}<br>"
            f"Rounds: {rounds}<br>"
            f"Connections: {G.degree(node)}"
        )
        nodes_data.append({
            "id":      node,
            "label":   node,
            "color":   color,
            "size":    round(size, 1),
            "title":   tooltip,
            "vcs":     vcs,
            "sectors": sectors,
            "hidden":  False,
        })

    edges_data = []
    for idx, (u, v, data) in enumerate(G.edges(data=True)):
        types = data.get("types", [])
        if "partner" in types and "founder" in types:
            color, width = "#a855f7", 2.5
        elif "partner" in types:
            color, width = "#3b82f6", 1.5
        else:
            color, width = "#f97316", 1.5
        edges_data.append({
            "id":     f"e{idx}",
            "from":   u,
            "to":     v,
            "color":  {"color": color, "opacity": 0.7},
            "width":  width,
            "title":  " + ".join(types),
            "hidden": False,
        })

    vc_colors_js     = json.dumps(VC_COLORS)
    sector_colors_js = json.dumps(SECTOR_COLORS)
    nodes_js         = json.dumps(nodes_data)
    edges_js         = json.dumps(edges_data)

    vc_buttons_html = "\n".join(
        f'<button class="vc-btn active" data-vc="{vc}" '
        f'style="--vc-color:{color}" onclick="toggleVC(this)">'
        f'<span class="dot"></span>{vc}</button>'
        for vc, color in VC_COLORS.items()
    )

    sector_buttons_html = "\n".join(
        f'<button class="vc-btn active" data-sector="{sector}" '
        f'style="--vc-color:{color}" onclick="toggleSector(this)">'
        f'<span class="dot"></span>{sector}</button>'
        for sector, color in SECTOR_COLORS.items()
    )

    sector_legend_html = "".join(
        f'<span class="ledot" style="background:{c}"></span>{s}<br>'
        for s, c in SECTOR_COLORS.items()
    )

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>VC Ecosystem</title>
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #1a1a2e; color: #eee; font-family: system-ui, sans-serif;
          display: flex; height: 100vh; overflow: hidden; }}

  #sidebar {{
    width: 220px; flex-shrink: 0; background: #11112a; padding: 14px;
    display: flex; flex-direction: column; gap: 10px; overflow-y: auto;
    border-right: 1px solid #333;
  }}
  #sidebar h2 {{ font-size: 13px; color: #aaa; text-transform: uppercase;
                 letter-spacing: .08em; }}

  .vc-btn {{
    display: flex; align-items: center; gap: 8px; width: 100%;
    background: #1e1e3a; border: 1px solid #444; border-radius: 6px;
    color: #eee; padding: 7px 10px; font-size: 13px; cursor: pointer;
    transition: opacity .15s, background .15s;
  }}
  .vc-btn .dot {{
    width: 11px; height: 11px; border-radius: 50%; flex-shrink: 0;
    background: var(--vc-color);
  }}
  .vc-btn.active  {{ border-color: var(--vc-color); background: #1e1e3a; }}
  .vc-btn.inactive {{ opacity: .4; background: #141428; border-color: #333; }}
  .vc-btn[draggable="true"] {{ cursor: grab; }}
  .vc-btn[draggable="true"]:active {{ cursor: grabbing; }}
  .vc-btn.drag-over {{ border-top: 2px solid #a855f7 !important; opacity: 1 !important; }}
  .drag-handle {{ color: #555; font-size: 10px; margin-right: 3px; line-height: 1; }}

  .divider {{ height: 1px; background: #333; }}

  .opt-row {{ display: flex; align-items: center; gap: 8px; font-size: 12px;
               color: #bbb; cursor: pointer; }}
  .opt-row input {{ cursor: pointer; accent-color: #888; }}

  #legend {{ font-size: 11px; color: #aaa; line-height: 1.8; }}
  .ledot {{ display: inline-block; width: 10px; height: 10px;
             border-radius: 50%; margin-right: 4px; }}
  .ledge {{ display: inline-block; width: 18px; height: 3px;
             border-radius: 2px; margin-right: 4px; vertical-align: middle; }}

  #btn-row {{ display: flex; gap: 6px; }}
  #btn-row button {{
    flex: 1; background: #2a2a4a; border: 1px solid #555; border-radius: 5px;
    color: #ccc; font-size: 11px; padding: 5px; cursor: pointer;
  }}
  #btn-row button:hover {{ background: #3a3a5a; }}

  #stats {{ font-size: 11px; color: #888; line-height: 1.6; }}

  #graph {{ flex: 1; }}

  .action-btn {{
    width: 100%; background: #2a2a4a; border: 1px solid #555; border-radius: 5px;
    color: #ccc; font-size: 12px; padding: 7px 10px; cursor: pointer; text-align: left;
  }}
  .action-btn:hover {{ background: #3a3a5a; }}
  .action-btn.active-focus {{ background: #3a1a4a; border-color: #a855f7; color: #d8b4fe; }}

  #grp-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 5px; }}
  .grp-btn {{
    background: #2a2a4a; border: 1px solid #555; border-radius: 5px;
    color: #ccc; font-size: 11px; padding: 6px 4px; cursor: pointer; text-align: center;
  }}
  .grp-btn:hover {{ background: #3a3a5a; }}
  .grp-btn.active-focus {{ background: #3a1a4a; border-color: #a855f7; color: #d8b4fe; }}

  #focus-hint {{
    font-size: 10px; color: #666; line-height: 1.5;
  }}
</style>
</head>
<body>

<div id="sidebar">
  <h2>VC Filter</h2>
  <div id="btn-row">
    <button onclick="setAll(true)">All on</button>
    <button onclick="setAll(false)">All off</button>
  </div>
  {vc_buttons_html}

  <div class="divider"></div>

  <label class="opt-row">
    <input type="checkbox" id="chk-unaffiliated" checked onchange="updateVisibility()">
    Show unaffiliated
  </label>
  <label class="opt-row">
    <input type="checkbox" id="chk-multi" checked onchange="updateVisibility()">
    Highlight multi-VC
  </label>

  <div class="divider"></div>

  <h2>Sector Filter</h2>
  <div id="btn-row">
    <button onclick="setSectorAll(true)">All on</button>
    <button onclick="setSectorAll(false)">All off</button>
  </div>
  <div id="sector-btn-list"></div>

  <div class="divider"></div>

  <label class="opt-row">
    <input type="checkbox" id="chk-same-sector" onchange="updateVisibility()">
    Same-sector edges only
  </label>

  <div class="divider"></div>

  <div id="legend">
    <b style="color:#eee">Node colour (VC)</b><br>
    {"".join(f'<span class="ledot" style="background:{c}"></span>{v}<br>' for v,c in VC_COLORS.items())}
    <span class="ledot" style="background:{MULTI_VC_COLOR}"></span>multi-VC<br>
    <span class="ledot" style="background:{NO_VC_COLOR}"></span>unaffiliated<br>
    <br>
    <b style="color:#eee">Sectors</b><br>
    {sector_legend_html}
    <br>
    <b style="color:#eee">Edge type</b><br>
    <span class="ledge" style="background:#3b82f6"></span>partner<br>
    <span class="ledge" style="background:#f97316"></span>founder<br>
    <span class="ledge" style="background:#a855f7"></span>both<br>
    <br>
    <b style="color:#eee">Node size</b> = funding
  </div>

  <div class="divider"></div>
  <h2>Tools</h2>
  <button class="action-btn" id="btn-spread" onclick="spreadClusters()">⊹ Spread clusters</button>
  <button class="action-btn" id="btn-focus" onclick="toggleFocusMode()">◎ Focus mode: off</button>
  <div id="focus-hint">Click a node to isolate its edges.<br>Click again or background to clear.</div>

  <div class="divider"></div>
  <h2>Group layout</h2>
  <div id="grp-row">
    <button class="grp-btn active-focus" id="grp-none"   onclick="setGroupMode('none')">None</button>
    <button class="grp-btn"              id="grp-vc"     onclick="setGroupMode('vc')">By VC</button>
    <button class="grp-btn"              id="grp-sector" onclick="setGroupMode('sector')">By Sector</button>
    <button class="grp-btn"              id="grp-both"   onclick="setGroupMode('both')">Both</button>
  </div>

  <div class="divider"></div>
  <div id="stats">Loading…</div>
</div>

<div id="graph"></div>

<script>
const ALL_NODES = new vis.DataSet({nodes_js});
const ALL_EDGES = new vis.DataSet({edges_js});
const VC_COLORS     = {vc_colors_js};
const SECTOR_COLORS = {sector_colors_js};
const MULTI_COLOR   = "{MULTI_VC_COLOR}";

// Pre-build lookups
const nodeVcs = {{}};
const nodeSectors = {{}};
ALL_NODES.forEach(n => {{
  nodeVcs[n.id]     = n.vcs     || [];
  nodeSectors[n.id] = n.sectors || [];
}});

const edgeEndpoints = {{}};
ALL_EDGES.forEach(e => {{ edgeEndpoints[e.id] = {{from: e.from, to: e.to}}; }});

// Active VC state
const vcActive = {{}};
document.querySelectorAll('[data-vc]').forEach(btn => {{
  vcActive[btn.dataset.vc] = true;
}});

// Active sector state — initialised from SECTOR_COLORS (buttons rendered dynamically)
const sectorActive = {{}};
Object.keys(SECTOR_COLORS).forEach(s => {{ sectorActive[s] = true; }});

// Sector ordering — drag to reorder; first matching sector = primary for grouping
let sectorOrder = Object.keys(SECTOR_COLORS);
let dragSector = null;

function renderSectorButtons() {{
  const list = document.getElementById('sector-btn-list');
  list.innerHTML = sectorOrder.map(sector => {{
    const color = SECTOR_COLORS[sector];
    const cls   = sectorActive[sector] ? 'active' : 'inactive';
    return `<button class="vc-btn ${{cls}}" data-sector="${{sector}}"
        style="--vc-color:${{color}}" draggable="true"
        onclick="toggleSector(this)"
        ondragstart="onSectorDragStart(event,'${{sector}}')"
        ondragover="onSectorDragOver(event)"
        ondragleave="onSectorDragLeave(event)"
        ondrop="onSectorDrop(event,'${{sector}}')"
        ondragend="onSectorDragEnd(event)">
      <span class="drag-handle">⠿</span>
      <span class="dot"></span>${{sector}}
    </button>`;
  }}).join('');
}}

function onSectorDragStart(e, sector) {{
  dragSector = sector;
  e.dataTransfer.effectAllowed = 'move';
}}
function onSectorDragOver(e) {{
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  e.currentTarget.classList.add('drag-over');
}}
function onSectorDragLeave(e) {{
  e.currentTarget.classList.remove('drag-over');
}}
function onSectorDragEnd(e) {{
  dragSector = null;
  document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
}}
function onSectorDrop(e, targetSector) {{
  e.preventDefault();
  e.currentTarget.classList.remove('drag-over');
  if (!dragSector || dragSector === targetSector) return;
  const fi = sectorOrder.indexOf(dragSector);
  const ti = sectorOrder.indexOf(targetSector);
  sectorOrder.splice(fi, 1);
  sectorOrder.splice(ti, 0, dragSector);
  dragSector = null;
  renderSectorButtons();
  if (activeLayout === 'sector' || activeLayout === 'both') {{
    groupLabels.length = 0;
    applyGroupLayout(activeLayout);
  }}
}}

function toggleSector(btn) {{
  const s = btn.dataset.sector;
  sectorActive[s] = !sectorActive[s];
  btn.classList.toggle('active',   sectorActive[s]);
  btn.classList.toggle('inactive', !sectorActive[s]);
  updateVisibility();
}}

function setSectorAll(on) {{
  document.querySelectorAll('[data-sector]').forEach(btn => {{
    sectorActive[btn.dataset.sector] = on;
    btn.classList.toggle('active',   on);
    btn.classList.toggle('inactive', !on);
  }});
  updateVisibility();
}}

// Focus state
let focusedNode = null;
let focusModeEnabled = false;

function toggleFocusMode() {{
  focusModeEnabled = !focusModeEnabled;
  const btn = document.getElementById('btn-focus');
  btn.textContent = `◎ Focus mode: ${{focusModeEnabled ? 'on' : 'off'}}`;
  btn.classList.toggle('active-focus', focusModeEnabled);
  if (!focusModeEnabled) {{
    focusedNode = null;
    updateVisibility();
  }}
}}

function toggleVC(btn) {{
  const vc = btn.dataset.vc;
  vcActive[vc] = !vcActive[vc];
  btn.classList.toggle('active',   vcActive[vc]);
  btn.classList.toggle('inactive', !vcActive[vc]);
  updateVisibility();
}}

function setAll(on) {{
  document.querySelectorAll('[data-vc]').forEach(btn => {{
    vcActive[btn.dataset.vc] = on;
    btn.classList.toggle('active',   on);
    btn.classList.toggle('inactive', !on);
  }});
  updateVisibility();
}}

function isNodeVisible(id) {{
  // VC filter
  const vcs = nodeVcs[id];
  const passesVC = (!vcs || vcs.length === 0)
    ? document.getElementById('chk-unaffiliated').checked
    : vcs.some(vc => vcActive[vc]);
  if (!passesVC) return false;

  // Sector filter — nodes with no sector are always shown
  const sectors = nodeSectors[id];
  const passesSector = (!sectors || sectors.length === 0)
    || sectors.some(s => sectorActive[s]);
  return passesSector;
}}

function updateVisibility() {{
  const showMultiHighlight = document.getElementById('chk-multi').checked;
  const visibleSet = new Set();

  const nodeUpdates = [];
  ALL_NODES.forEach(n => {{
    const visible = isNodeVisible(n.id);
    if (visible) visibleSet.add(n.id);

    // Recompute color: if multi-VC highlight is off, use single-VC color or grey
    let color = n.color;
    if (!showMultiHighlight && (n.vcs || []).length > 1) {{
      const known = (n.vcs || []).filter(v => VC_COLORS[v]);
      color = known.length ? VC_COLORS[known[0]] : "{NO_VC_COLOR}";
    }}
    nodeUpdates.push({{ id: n.id, hidden: !visible, color }});
  }});
  ALL_NODES.update(nodeUpdates);

  const sameSectorOnly = document.getElementById('chk-same-sector').checked;
  const edgeUpdates = [];
  ALL_EDGES.forEach(e => {{
    const ep = edgeEndpoints[e.id];
    const bothVisible = visibleSet.has(ep.from) && visibleSet.has(ep.to);
    const passesFocus = !focusModeEnabled || focusedNode === null ||
                        ep.from === focusedNode || ep.to === focusedNode;
    let passesSector = true;
    if (sameSectorOnly) {{
      const uSectors = new Set(nodeSectors[ep.from] || []);
      const vSectors = nodeSectors[ep.to] || [];
      passesSector = vSectors.some(s => uSectors.has(s));
    }}
    edgeUpdates.push({{ id: e.id, hidden: !(bothVisible && passesFocus && passesSector) }});
  }});
  ALL_EDGES.update(edgeUpdates);

  const visibleEdges = edgeUpdates.filter(e => !e.hidden).length;
  const focusLabel = focusModeEnabled && focusedNode ? `<br>Focused: ${{focusedNode}}` : '';
  document.getElementById('stats').innerHTML =
    `Visible nodes: ${{visibleSet.size}}<br>Visible edges: ${{visibleEdges}}${{focusLabel}}`;
}}

// Render draggable sector buttons
renderSectorButtons();

// Init vis network
const container = document.getElementById('graph');
const network = new vis.Network(container,
  {{ nodes: ALL_NODES, edges: ALL_EDGES }},
  {{
    physics: {{
      solver: 'barnesHut',
      barnesHut: {{ gravitationalConstant: -8000, centralGravity: 0.3,
                    springLength: 120, damping: 0.09 }},
      stabilization: {{ iterations: 200 }},
    }},
    nodes: {{
      font: {{ color: '#ffffff', size: 11 }},
      borderWidth: 0,
      shape: 'dot',
    }},
    edges: {{
      smooth: {{ type: 'continuous', roundness: 0.2 }},
      arrows: {{ to: false }},
    }},
    interaction: {{
      hover: true,
      tooltipDelay: 100,
      hideEdgesOnDrag: true,
    }},
  }}
);

network.once('stabilizationIterationsDone', () => {{
  network.setOptions({{ physics: {{ enabled: false }} }});
  updateVisibility();
}});

// Draw group labels on the canvas — immune to physics/DataSet events
network.on('afterDrawing', function(ctx) {{
  if (!groupLabels.length) return;
  const scale = network.getScale();
  ctx.save();
  ctx.textAlign = 'center';
  for (const lbl of groupLabels) {{
    ctx.font = `bold ${{Math.round((lbl.size || 15) / scale)}}px system-ui, sans-serif`;
    ctx.fillStyle = lbl.color || '#e2e8f0';
    ctx.textBaseline = lbl.baseline || 'bottom';
    ctx.fillText(lbl.text, lbl.gx, lbl.gy);
  }}
  ctx.restore();
}});

// Click handler: focus mode node selection
network.on('click', function(params) {{
  if (!focusModeEnabled) return;
  if (params.nodes.length > 0) {{
    const clicked = params.nodes[0];
    focusedNode = (focusedNode === clicked) ? null : clicked;
  }} else if (params.edges.length === 0) {{
    focusedNode = null;
  }}
  updateVisibility();
}});

// ── Unified layout management ─────────────────────────────────────────────────
// activeLayout: 'none' | 'spread' | 'vc' | 'sector' | 'both'
let activeLayout = 'none';
let layoutSavedPositions = null;
let groupLabels = []; // {{text, gx, gy, size, color, baseline}} — drawn on canvas via afterDrawing

function deactivateLayout() {{
  if (activeLayout === 'none') return;
  if (layoutSavedPositions) {{
    ALL_NODES.update(
      Object.entries(layoutSavedPositions).map(([id, pos]) => ({{ id, x: pos.x, y: pos.y }}))
    );
    layoutSavedPositions = null;
  }}
  groupLabels.length = 0;
  const spreadBtn = document.getElementById('btn-spread');
  spreadBtn.textContent = '⊹ Spread clusters';
  spreadBtn.classList.remove('active-focus');
  document.querySelectorAll('.grp-btn').forEach(b => b.classList.remove('active-focus'));
  document.getElementById('grp-none').classList.add('active-focus');
  activeLayout = 'none';
}}

function activateLayout(mode) {{
  if (activeLayout !== 'none') deactivateLayout();
  layoutSavedPositions = network.getPositions();
  activeLayout = mode;
  if (mode === 'spread') {{
    const btn = document.getElementById('btn-spread');
    btn.textContent = '⊹ Spread clusters: on';
    btn.classList.add('active-focus');
    applySpreadLayout();
  }} else {{
    document.getElementById('grp-none').classList.remove('active-focus');
    document.getElementById('grp-' + mode).classList.add('active-focus');
    applyGroupLayout(mode);
  }}
}}

function spreadClusters() {{
  if (activeLayout === 'spread') {{
    deactivateLayout();
    network.fit({{ animation: {{ duration: 600, easingFunction: 'easeInOutQuad' }} }});
  }} else {{
    activateLayout('spread');
  }}
}}

function setGroupMode(mode) {{
  if (mode === activeLayout) return;
  if (mode === 'none') {{
    deactivateLayout();
    network.fit({{ animation: {{ duration: 600, easingFunction: 'easeInOutQuad' }} }});
  }} else {{
    activateLayout(mode);
  }}
}}

function applySpreadLayout() {{
  const positions = layoutSavedPositions;
  const visibleNodes = [];
  ALL_NODES.forEach(n => {{ if (!n.hidden) visibleNodes.push(n.id); }});
  const visibleSet = new Set(visibleNodes);

  const adj = {{}};
  visibleNodes.forEach(id => {{ adj[id] = []; }});
  ALL_EDGES.forEach(e => {{
    if (visibleSet.has(e.from) && visibleSet.has(e.to)) {{
      adj[e.from].push(e.to);
      adj[e.to].push(e.from);
    }}
  }});

  const visited = new Set();
  const components = [];
  for (const id of visibleNodes) {{
    if (visited.has(id)) continue;
    const comp = [];
    const queue = [id];
    while (queue.length) {{
      const node = queue.shift();
      if (visited.has(node)) continue;
      visited.add(node);
      comp.push(node);
      (adj[node] || []).forEach(nb => {{ if (!visited.has(nb)) queue.push(nb); }});
    }}
    components.push(comp);
  }}
  components.sort((a, b) => b.length - a.length);

  const centroids = components.map(comp => {{
    const xs = comp.map(id => (positions[id] || {{}}).x || 0);
    const ys = comp.map(id => (positions[id] || {{}}).y || 0);
    return {{ x: xs.reduce((a,b) => a+b, 0)/comp.length, y: ys.reduce((a,b) => a+b, 0)/comp.length }};
  }});

  const cols = Math.ceil(Math.sqrt(components.length));
  const spacing = 900;
  const nodeUpdates = [];
  components.forEach((comp, i) => {{
    const col = i % cols, row = Math.floor(i / cols);
    const tx = (col - (cols-1)/2) * spacing;
    const ty = (row - (Math.ceil(components.length/cols)-1)/2) * spacing;
    const dx = tx - centroids[i].x, dy = ty - centroids[i].y;
    comp.forEach(id => {{
      const pos = positions[id] || {{ x:0, y:0 }};
      nodeUpdates.push({{ id, x: pos.x+dx, y: pos.y+dy }});
    }});
  }});

  network.setOptions({{ physics: {{ enabled: false }} }});
  ALL_NODES.update(nodeUpdates);
  network.fit({{ animation: {{ duration: 600, easingFunction: 'easeInOutQuad' }} }});
}}

function groupArrange(groups, getCentroid, getLabelText) {{
  const updates = [];
  for (const [key, nodeIds] of Object.entries(groups)) {{
    if (!nodeIds.length) continue;
    const center = getCentroid(key);
    const n = nodeIds.length;
    const cols = Math.ceil(Math.sqrt(n));
    const gap = 65;
    nodeIds.forEach((id, idx) => {{
      const col = idx % cols, row = Math.floor(idx / cols);
      updates.push({{
        id,
        x: center.x + (col - (cols-1)/2) * gap,
        y: center.y + (row - (Math.ceil(n/cols)-1)/2) * gap,
      }});
    }});
    if (getLabelText) {{
      const yOffset = Math.ceil(Math.sqrt(n) / 2) * gap + 80;
      groupLabels.push({{ text: getLabelText(key), gx: center.x, gy: center.y - yOffset, size: 17, color: '#e2e8f0' }});
    }}
  }}
  network.setOptions({{ physics: {{ enabled: false }} }});
  ALL_NODES.update(updates);
  network.fit({{ animation: {{ duration: 600, easingFunction: 'easeInOutQuad' }} }});
}}

function applyGroupLayout(mode) {{
  const VC_ORDER     = [...Object.keys(VC_COLORS), '__multi__', '__none__'];
  const SECTOR_ORDER = [...sectorOrder, '__none__'];  // respects user drag order

  function getVcKey(n) {{
    const known = (n.vcs || []).filter(v => VC_COLORS[v]);
    if (!known.length) return '__none__';
    if (known.length > 1) return '__multi__';
    return known[0];
  }}
  function getSectorKey(n) {{
    const has = new Set(n.sectors || []);
    return sectorOrder.find(s => has.has(s)) || '__none__';
  }}

  if (mode === 'vc') {{
    const groups = {{}};
    ALL_NODES.forEach(n => {{ const k = getVcKey(n); (groups[k] = groups[k] || []).push(n.id); }});
    const keys = VC_ORDER.filter(k => groups[k]?.length);
    const R = Math.max(1600, keys.length * 260);
    const centroids = Object.fromEntries(keys.map((k, i) => {{
      const a = 2*Math.PI*i/keys.length - Math.PI/2;
      return [k, {{ x: R*Math.cos(a), y: R*Math.sin(a) }}];
    }}));
    const vcLabel = k => k === '__none__' ? 'Unaffiliated' : k === '__multi__' ? 'Multi-VC' : k;
    groupArrange(groups, k => centroids[k], vcLabel);
  }}

  else if (mode === 'sector') {{
    const groups = {{}};
    ALL_NODES.forEach(n => {{ const k = getSectorKey(n); (groups[k] = groups[k] || []).push(n.id); }});
    const keys = SECTOR_ORDER.filter(k => groups[k]?.length);
    const R = Math.max(1800, keys.length * 280);
    const centroids = Object.fromEntries(keys.map((k, i) => {{
      const a = 2*Math.PI*i/keys.length - Math.PI/2;
      return [k, {{ x: R*Math.cos(a), y: R*Math.sin(a) }}];
    }}));
    const secLabel = k => k === '__none__' ? 'No Sector' : k;
    groupArrange(groups, k => centroids[k], secLabel);
  }}

  else if (mode === 'both') {{
    const cells = {{}};
    ALL_NODES.forEach(n => {{
      const vk = getVcKey(n), sk = getSectorKey(n), key = vk + '||' + sk;
      if (!cells[key]) cells[key] = {{ vk, sk, nodes: [] }};
      cells[key].nodes.push(n.id);
    }});
    const usedVcs     = [...new Set(Object.values(cells).map(c => c.vk))];
    const usedSectors = [...new Set(Object.values(cells).map(c => c.sk))];
    usedVcs.sort((a,b) => VC_ORDER.indexOf(a) - VC_ORDER.indexOf(b));
    usedSectors.sort((a,b) => SECTOR_ORDER.indexOf(a) - SECTOR_ORDER.indexOf(b));
    const vcIdx = Object.fromEntries(usedVcs.map((v,i) => [v,i]));
    const sIdx  = Object.fromEntries(usedSectors.map((s,i) => [s,i]));
    const cellW = 700, cellH = 700;
    const offX = -(usedVcs.length-1)/2*cellW;
    const offY = -(usedSectors.length-1)/2*cellH;
    const flatGroups = Object.fromEntries(Object.entries(cells).map(([k,c]) => [k, c.nodes]));
    groupArrange(flatGroups, key => ({{
      x: offX + vcIdx[cells[key].vk] * cellW,
      y: offY + sIdx[cells[key].sk]  * cellH,
    }}), null);

    // VC column headers (top) and sector row headers (left) — drawn on canvas
    usedVcs.forEach(v => {{
      groupLabels.push({{
        text: v === '__none__' ? 'Unaffiliated' : v === '__multi__' ? 'Multi-VC' : v,
        gx: offX + vcIdx[v] * cellW, gy: offY - cellH * 0.6,
        size: 15, color: '#94a3b8',
      }});
    }});
    usedSectors.forEach(s => {{
      groupLabels.push({{
        text: s === '__none__' ? 'No Sector' : s,
        gx: offX - cellW * 0.58, gy: offY + sIdx[s] * cellH,
        size: 13, color: '#94a3b8', baseline: 'middle',
      }});
    }});
    network.redraw();
  }}
}}
</script>
</body>
</html>"""

    out = os.path.join(SCRIPT_DIR, "ecosystem.html")
    with open(out, "w") as f:
        f.write(html)
    print(f"  ecosystem.html written ({G.number_of_nodes()} nodes, {G.number_of_edges()} edges)")


# ── 2. VC co-investment graph ─────────────────────────────────────────────────

def make_coinvestment_html(G: nx.Graph):
    portfolios: dict[str, set[str]] = {}
    for node, data in G.nodes(data=True):
        for vc in data.get("vcs", []):
            portfolios.setdefault(vc, set()).add(node)

    vcs = list(portfolios.keys())
    net = Network(height="700px", width="100%", bgcolor="#1a1a2e", font_color="white")
    net.barnes_hut(gravity=-3000, spring_length=200)

    max_portfolio = max(len(s) for s in portfolios.values())
    for vc in vcs:
        size    = 20 + 40 * len(portfolios[vc]) / max_portfolio
        color   = VC_COLORS.get(vc, NO_VC_COLOR)
        tooltip = f"<b>{vc}</b><br>Portfolio: {len(portfolios[vc])} companies"
        net.add_node(vc, label=vc, color=color, size=size, title=tooltip)

    weights = []
    for i in range(len(vcs)):
        for j in range(i + 1, len(vcs)):
            shared = portfolios[vcs[i]] & portfolios[vcs[j]]
            if shared:
                weights.append(len(shared))

    max_w = max(weights) if weights else 1
    for i in range(len(vcs)):
        for j in range(i + 1, len(vcs)):
            a, b   = vcs[i], vcs[j]
            shared = portfolios[a] & portfolios[b]
            if shared:
                w     = len(shared)
                width = 1 + 9 * w / max_w
                net.add_edge(a, b, width=width, color="#aaaaaa",
                             title=f"{w} shared: {', '.join(sorted(shared)[:10])}{'…' if len(shared)>10 else ''}")

    out = os.path.join(SCRIPT_DIR, "coinvestment.html")
    net.save_graph(out)
    print(f"  coinvestment.html written")


# ── 3. GEXF export for Gephi ─────────────────────────────────────────────────

def make_gexf(G: nx.Graph):
    # GEXF wants simple string/numeric attrs
    G2 = nx.Graph()
    for node, data in G.nodes(data=True):
        G2.add_node(node,
                    vcs=",".join(data.get("vcs", [])),
                    total_funding=float(data.get("total_funding", 0)),
                    num_rounds=len(data.get("rounds", {})))
    for u, v, data in G.edges(data=True):
        G2.add_edge(u, v, relationship=",".join(data.get("types", [])))

    out = os.path.join(SCRIPT_DIR, "company_graph.gexf")
    nx.write_gexf(G2, out)
    print(f"  company_graph.gexf written (open in Gephi)")


# ── 4. Co-investment heatmap ──────────────────────────────────────────────────

def make_coinvestment_heatmap(G: nx.Graph):
    portfolios: dict[str, set[str]] = {}
    for node, data in G.nodes(data=True):
        for vc in data.get("vcs", []):
            portfolios.setdefault(vc, set()).add(node)

    vcs    = sorted(portfolios.keys())
    n      = len(vcs)
    matrix = np.zeros((n, n))
    for i, a in enumerate(vcs):
        for j, b in enumerate(vcs):
            if i != j:
                matrix[i, j] = len(portfolios[a] & portfolios[b])

    fig, ax = plt.subplots(figsize=(8, 7))
    im = ax.imshow(matrix, cmap="YlOrRd")
    ax.set_xticks(range(n)); ax.set_xticklabels(vcs, rotation=45, ha="right")
    ax.set_yticks(range(n)); ax.set_yticklabels(vcs)
    plt.colorbar(im, ax=ax, label="# shared companies")
    for i in range(n):
        for j in range(n):
            if matrix[i, j] > 0:
                ax.text(j, i, int(matrix[i, j]), ha="center", va="center", fontsize=8,
                        color="black" if matrix[i, j] < matrix.max() * 0.6 else "white")
    ax.set_title("VC Co-investment: Shared Portfolio Companies")
    plt.tight_layout()
    out = os.path.join(SCRIPT_DIR, "coinvestment_heatmap.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"  coinvestment_heatmap.png written")


# ── 5. Degree distribution ────────────────────────────────────────────────────

def make_degree_distribution(G: nx.Graph):
    degrees = sorted([d for _, d in G.degree()], reverse=True)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    axes[0].bar(range(len(degrees)), degrees, color="#1f77b4", width=1.0)
    axes[0].set_xlabel("Node rank"); axes[0].set_ylabel("Degree")
    axes[0].set_title("Degree distribution (sorted)")

    axes[1].hist(degrees, bins=30, color="#ff7f0e", edgecolor="white")
    axes[1].set_xlabel("Degree"); axes[1].set_ylabel("Count")
    axes[1].set_title("Degree histogram")

    # Top-10 by degree
    top10 = sorted(G.degree(), key=lambda x: -x[1])[:10]
    print("\n  Top 10 companies by degree (most connections):")
    for name, deg in top10:
        vcs = G.nodes[name].get("vcs", [])
        print(f"    {name:<40} degree={deg}  VCs={vcs}")

    plt.tight_layout()
    out = os.path.join(SCRIPT_DIR, "degree_distribution.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"  degree_distribution.png written")


# ── 6. Sector × VC proportion table ──────────────────────────────────────────

def make_sector_vc_table(G: nx.Graph):
    sector_map: dict[str, list[str]] = {}
    for fname in ["sector_map.json", "talent_fac_sector_map.json", "unlabelled_sector_map.json"]:
        fpath = os.path.join(SCRIPT_DIR, fname)
        if os.path.exists(fpath):
            with open(fpath) as f:
                sector_map.update(json.load(f))

    # Build per-VC portfolio sets (only tracked VCs)
    portfolios: dict[str, set[str]] = {}
    for node, data in G.nodes(data=True):
        for vc in data.get("vcs", []):
            if vc in VC_COLORS:
                portfolios.setdefault(vc, set()).add(node)

    vcs     = list(VC_COLORS.keys())
    sectors = list(SECTOR_COLORS.keys())

    # For each sector: list of (vc, proportion, count) sorted desc by proportion
    table: dict[str, list[tuple[str, float, int]]] = {}
    for sector in sectors:
        row = []
        for vc in vcs:
            port = portfolios.get(vc, set())
            count = sum(1 for c in port if sector in sector_map.get(c, []))
            prop  = count / len(port) if port else 0.0
            row.append((vc, prop, count))
        row.sort(key=lambda x: -x[1])
        table[sector] = row

    # Hex → rgba helper for subtle cell backgrounds
    def hex_to_rgba(h: str, a: float) -> str:
        r = int(h[1:3], 16)
        g = int(h[3:5], 16)
        b = int(h[5:7], 16)
        return f"rgba({r},{g},{b},{a})"

    vc_colors_js     = json.dumps(VC_COLORS)
    sector_colors_js = json.dumps(SECTOR_COLORS)

    rows_html = ""
    for sector in sectors:
        s_color = SECTOR_COLORS[sector]
        cells = ""
        for rank, (vc, prop, count) in enumerate(table[sector]):
            vc_color = VC_COLORS[vc]
            bg = hex_to_rgba(vc_color, 0.15) if prop > 0 else "transparent"
            pct_str = f"{prop*100:.1f}%"
            bar_w   = round(prop * 100, 1)
            opacity = "1" if prop > 0 else "0.25"
            cells += f"""
            <td style="opacity:{opacity}">
              <div class="cell-inner">
                <span class="rank">#{rank+1}</span>
                <span class="dot" style="background:{vc_color}"></span>
                <span class="vc-name">{vc}</span>
                <span class="pct">{pct_str}</span>
                <span class="cnt">({count})</span>
              </div>
              <div class="bar" style="width:{bar_w}%;background:{vc_color};opacity:0.5"></div>
            </td>"""
        rows_html += f"""
        <tr>
          <td class="sector-cell">
            <span class="sdot" style="background:{s_color}"></span>{sector}
          </td>
          {cells}
        </tr>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Sector × VC Proportion Table</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #1a1a2e; color: #eee; font-family: system-ui, sans-serif;
          padding: 32px; }}
  h1 {{ font-size: 20px; color: #aaa; margin-bottom: 6px; font-weight: 500; }}
  p.sub {{ font-size: 12px; color: #666; margin-bottom: 24px; }}
  table {{ border-collapse: collapse; width: 100%; table-layout: fixed; }}
  th {{ background: #11112a; color: #888; font-size: 11px; font-weight: 500;
        text-transform: uppercase; letter-spacing: .06em;
        padding: 10px 12px; text-align: left; border-bottom: 1px solid #333; }}
  td {{ padding: 0; border-bottom: 1px solid #1e1e3a; vertical-align: top;
        position: relative; overflow: hidden; }}
  td.sector-cell {{
    padding: 10px 12px; font-size: 13px; font-weight: 500; color: #ddd;
    white-space: nowrap; background: #11112a; width: 200px;
    border-right: 1px solid #333;
  }}
  .sdot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%;
            margin-right: 7px; vertical-align: middle; }}
  .cell-inner {{
    display: flex; align-items: center; gap: 5px;
    padding: 9px 10px 4px; font-size: 12px;
  }}
  .rank  {{ color: #555; font-size: 10px; width: 20px; flex-shrink: 0; }}
  .dot   {{ width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}
  .vc-name {{ flex: 1; color: #ccc; }}
  .pct   {{ color: #eee; font-weight: 600; font-size: 13px; }}
  .cnt   {{ color: #666; font-size: 11px; }}
  .bar   {{ height: 3px; margin: 2px 0 6px; border-radius: 2px; transition: width .3s; }}
  tr:hover td {{ background: #1e1e2e !important; }}
</style>
</head>
<body>
<h1>Sector × VC Proportion</h1>
<p class="sub">For each sector, VCs ranked by proportion of their portfolio in that sector.
  Count = companies in portfolio tagged with that sector.</p>
<table>
  <thead>
    <tr>
      <th>Sector</th>
      {"".join(f"<th>#{i+1}</th>" for i in range(len(vcs)))}
    </tr>
  </thead>
  <tbody>
    {rows_html}
  </tbody>
</table>
</body>
</html>"""

    out = os.path.join(SCRIPT_DIR, "sector_vc_table.html")
    with open(out, "w") as f:
        f.write(html)
    print(f"  sector_vc_table.html written")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("Loading graph...")
    G = load_graph()
    print(f"  {G.number_of_nodes()} nodes, {G.number_of_edges()} edges\n")

    print("Generating visualizations:")
    make_ecosystem_html(G)
    make_coinvestment_html(G)
    make_gexf(G)
    make_coinvestment_heatmap(G)
    make_degree_distribution(G)
    make_sector_vc_table(G)
    print("\nDone. Open ecosystem.html, coinvestment.html, and sector_vc_table.html in your browser.")


if __name__ == "__main__":
    main()
