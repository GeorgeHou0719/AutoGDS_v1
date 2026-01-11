from __future__ import annotations

import time
from pathlib import Path
import re
from typing import Dict, List, Tuple

from autogds.journal import RunJournal
from autogds.schema import DesignBrief, Option
from autogds.workspace import RunWorkspace, write_json, write_text
from autogds.picker import choose_option
from autogds.dotgen import blueprint_to_dot

from autogds.catalog_scan import scan_python_catalog
from autogds.catalog_rank import rank_catalog
from autogds.role_vocab import normalize_role

from autogds.topology import build_topology_plan, topology_to_dot
from autogds.blueprint_bind import bind_plan_to_blueprint
from autogds.verify import verify_blueprint
from autogds.netlist_emit import blueprint_to_netlist
from autogds.layout_flow import normalize_netlist
from autogds.layout_footprint import extract_footprints
from autogds.layout_place import place_instances
from autogds.layout_align import align_instances
from autogds.layout_route import route_links
from autogds.layout_precheck import precheck_layout
from autogds.layout_emit import emit_gds
from autogds.layout_report import build_layout_report


def _components_only_filter(symbol: str, source_file: str) -> bool:
    s = (symbol or "").lower()
    f = (source_file or "").lower()

    if _is_model_symbol(s):
        return False
    if "template" in s or "templates" in s:
        return False
    if "template" in f or "templates" in f:
        return False

    if "components" in f:
        return True

    return False


def _is_model_symbol(symbol: str) -> bool:
    if not symbol:
        return False
    s = symbol.lower()
    return bool(re.search(r":get_model(\w+)?$", s))


def _filter_catalog_components_only(catalog) -> Tuple[list, bool]:
    kept = [c for c in catalog if _components_only_filter(c.symbol, c.source_file)]
    if kept:
        return kept, True
    return catalog, False


def _tokenize(text: str) -> List[str]:
    cleaned = re.sub(r"[^a-z0-9_]+", " ", (text or "").lower()).strip()
    return [t for t in cleaned.split() if t]


def _expand_query_with_role(role: str, query: str) -> str:
    t = (role or "").lower()
    extras: List[str] = []
    if "edge coupler" in t:
        extras.extend(["edge_coupler", "edge"])
    if "directional coupler" in t:
        extras.extend(["directional_coupler", "coupler"])
    if "coupler" in t:
        extras.append("coupler")
    if "mmi" in t:
        extras.append("mmi")
    if "splitter" in t:
        extras.append("splitter")
    if not extras:
        return query
    return f"{query} " + " ".join(extras)


def _count_keyword_hits(haystack: str, keywords: List[str]) -> int:
    if not haystack or not keywords:
        return 0
    hay = haystack.lower()
    return sum(1 for kw in keywords if kw and kw in hay)


def _rerank_options_with_contract(
    options: List[Option],
    entry_map: Dict[Tuple[str, str], object],
    node: object,
    query: str,
) -> List[Option]:
    if not options:
        return options

    query_tokens = _tokenize(query)
    required_port_form = getattr(node, "required_port_form", None)

    reranked: List[Option] = []
    for opt in options:
        entry = entry_map.get((opt.symbol, opt.source_file))
        breakdown = {"base_score": opt.score}
        bonus = 0.0

        contract = getattr(entry, "contract", None) if entry else None
        if contract:
            if required_port_form and contract.port_form and contract.port_form == required_port_form:
                bonus += 0.30
                breakdown["port_form_match"] = 0.30
            else:
                breakdown["port_form_match"] = 0.0

            label_hits = 0
            for label in contract.node_labels or []:
                label_tokens = _tokenize(str(label))
                if any(tok in query_tokens for tok in label_tokens):
                    label_hits += 1
            label_bonus = 0.05 * min(label_hits, 6)
            bonus += label_bonus
            breakdown["label_hits"] = label_hits
            breakdown["label_bonus"] = round(label_bonus, 4)

            spec_text = " ".join(
                [f"{k} {v}" for k, v in (contract.spec or {}).items()]
            )
            spec_hits = _count_keyword_hits(spec_text, query_tokens)
            spec_bonus = 0.01 * min(spec_hits, 10)
            bonus += spec_bonus
            breakdown["spec_hits"] = spec_hits
            breakdown["spec_bonus"] = round(spec_bonus, 4)
        else:
            breakdown["port_form_match"] = 0.0
            breakdown["label_hits"] = 0
            breakdown["label_bonus"] = 0.0
            breakdown["spec_hits"] = 0
            breakdown["spec_bonus"] = 0.0

        new_score = opt.score + bonus
        extras = dict(opt.extras or {})
        extras["score_breakdown"] = breakdown

        reranked.append(
            Option(
                symbol=opt.symbol,
                source_file=opt.source_file,
                score=new_score,
                rationale=opt.rationale,
                extras=extras,
            )
        )

    reranked.sort(key=lambda o: o.score, reverse=True)
    return reranked


def _ensure_keyword_candidates(
    opts: List[Option],
    catalog: List[object],
    query: str,
    keywords: List[str],
    max_add: int = 3,
) -> List[Option]:
    q = (query or "").lower()
    if not any(k in q for k in keywords):
        return opts

    existing = {(o.symbol, o.source_file) for o in opts}
    has_kw = any(any(k in (o.symbol or "").lower() for k in keywords) for o in opts)
    if has_kw:
        return opts

    added: List[Option] = []
    for e in catalog:
        hay = f"{e.symbol} {e.doc}".lower()
        if any(k in hay for k in keywords):
            key = (e.symbol, e.source_file)
            if key in existing:
                continue
            added.append(
                Option(
                    symbol=e.symbol,
                    source_file=e.source_file,
                    score=0.0,
                    rationale="Keyword fallback: ensure relevant components appear in options.",
                )
            )
            existing.add(key)
            if len(added) >= max_add:
                break

    return opts + added


def run_skeleton(
    brief: DesignBrief,
    ws: RunWorkspace,
    jr: RunJournal,
    non_interactive: bool,
    catalog_root: Path,
) -> Dict[str, str]:
    artifacts: Dict[str, str] = {}
    wiring_plan = []

    catalog_root = Path(catalog_root).expanduser().resolve()
    if not catalog_root.exists() or not catalog_root.is_dir():
        raise ValueError(f"--catalog must be an existing directory: {catalog_root}")

    # 0) scan catalog (Python docstrings)
    t0 = time.perf_counter()
    catalog_raw = scan_python_catalog(catalog_root)
    catalog_raw = [c for c in catalog_raw if not _is_model_symbol(c.symbol)]
    scan_ms = int((time.perf_counter() - t0) * 1000)
    jr.log("catalog", "scanned", extra={"root": str(catalog_root), "count": len(catalog_raw), "ms": scan_ms})

    if not catalog_raw:
        jr.log("catalog", "empty", note="No docstrings found in catalog directory.")
        raise RuntimeError(f"No catalog entries found under {catalog_root}. Provide a directory with docstrings.")

    catalog, components_only_ok = _filter_catalog_components_only(catalog_raw)
    jr.log(
        "catalog",
        "filtered",
        extra={"components_only": components_only_ok, "count_kept": len(catalog), "count_raw": len(catalog_raw)},
    )
    entry_map = {(c.symbol, c.source_file): c for c in catalog}

    index_path = ws.catalog / "index.json"
    write_json(index_path, [c.model_dump() for c in catalog])
    artifacts["catalog_index"] = str(index_path)
    jr.log("catalog", "saved", artifacts={"path": str(index_path)})

    # Capture special blocks into wiring_plan (unchanged behavior)
    for idx, bh in enumerate(brief.blocks):
        nr = normalize_role(bh.role)
        if nr.canonical in {"interconnect", "io_port"}:
            wiring_plan.append(
                {
                    "block_index": idx,
                    "role_raw": bh.role,
                    "role_canonical": nr.canonical,
                    "role_variant": nr.variant,
                    "count": bh.count,
                    "notes": bh.notes,
                }
            )
            jr.log("wiring", "captured", extra={"block_index": idx, "canonical": nr.canonical})

    wiring_path = ws.root / "wiring_plan.json"
    write_json(wiring_path, wiring_plan)
    artifacts["wiring_plan"] = str(wiring_path)
    jr.log("wiring", "saved", artifacts={"path": str(wiring_path)}, extra={"count": len(wiring_plan)})

    # 1) topo-first: build abstract topology skeleton
    plan = build_topology_plan(brief)
    plan_path = ws.root / "topology_plan.json"
    write_json(plan_path, plan.model_dump())
    artifacts["topology_plan"] = str(plan_path)
    jr.log("topology", "saved", artifacts={"path": str(plan_path), "nodes": len(plan.nodes), "intents": len(plan.intents)})

    topo_dot = topology_to_dot(plan)
    topo_dot_path = ws.root / "topology.dot"
    write_text(topo_dot_path, topo_dot)
    artifacts["topology_dot"] = str(topo_dot_path)
    jr.log("topology", "dot_saved", artifacts={"path": str(topo_dot_path)})

    # 2) per-node retrieval + selection (components-only)
    chosen: Dict[str, Option] = {}
    selections = []
    cache: Dict[str, Option] = {}

    global_context = " ".join([brief.title or "", brief.summary or "", brief.objective.target_behavior or ""]).strip()

    for node in plan.nodes:
        nr = normalize_role(node.role_raw)
        query_base = nr.to_query()
        query = _expand_query_with_role(node.role_raw, query_base)
        if node.notes:
            query = f"{query} {node.notes}"
        if global_context:
            query = f"{query} {global_context}"

        cache_key = f"{nr.canonical}||{node.notes or ''}||{global_context}"
        if cache_key in cache:
            picked = cache[cache_key]
            chosen[node.node_id] = picked
            selections.append(
                {
                    "node_id": node.node_id,
                    "role_raw": node.role_raw,
                    "role_canonical": node.role_canonical,
                    "role_variant": node.role_variant,
                    "query": query,
                    "selected": picked.model_dump(),
                    "selection_meta": {"mode": "cache"},
                }
            )
            continue

        required_port_form = getattr(node, "required_port_form", None)
        catalog_for_node = catalog
        if required_port_form:
            matching = [
                c
                for c in catalog
                if getattr(c, "contract", None)
                and getattr(c.contract, "port_form", None) == required_port_form
            ]
            if matching:
                catalog_for_node = matching

        t1 = time.perf_counter()
        try:
            opts = rank_catalog(query=query, catalog=catalog_for_node, top_k=12)
        except Exception as e:
            jr.log("retrieval", "rank_error", note=str(e), extra={"query": query})
            opts = []
        rank_ms = int((time.perf_counter() - t1) * 1000)
        jr.log("retrieval", "ranked", extra={"query": query, "k": len(opts), "ms": rank_ms, "node": node.node_id})

        if not opts:
            fallback_n = min(12, len(catalog))
            opts = [
                Option(
                    symbol=catalog[i].symbol,
                    source_file=catalog[i].source_file,
                    score=0.0,
                    rationale="Fallback: no good match found; showing catalog head.",
                )
                for i in range(fallback_n)
            ]
            jr.log("retrieval", "fallback", extra={"query": query, "k": len(opts), "node": node.node_id})

        opts = _ensure_keyword_candidates(
            opts=opts,
            catalog=catalog,
            query=query,
            keywords=["grating", "grating_coupler", "gc"],
            max_add=3,
        )
        opts = _ensure_keyword_candidates(
            opts=opts,
            catalog=catalog,
            query=query,
            keywords=["edge", "edge_coupler"],
            max_add=3,
        )

        opts = _rerank_options_with_contract(options=opts, entry_map=entry_map, node=node, query=query)

        opt_path = ws.root / f"options_node_{node.node_id}.json"
        write_json(opt_path, [o.model_dump() for o in opts])
        artifacts[f"options_node_{node.node_id}"] = str(opt_path)
        jr.log("options", "saved", artifacts={"path": str(opt_path)}, extra={"node": node.node_id, "role": node.role_raw})

        picked, pick_meta = choose_option(
            title=f"Node {node.node_id}: {node.role_raw}",
            options=opts,
            non_interactive=non_interactive,
            default_index=0,
        )

        cache[cache_key] = picked
        chosen[node.node_id] = picked
        selections.append(
            {
                "node_id": node.node_id,
                "role_raw": node.role_raw,
                "role_canonical": node.role_canonical,
                "role_variant": node.role_variant,
                "query": query,
                "selected": picked.model_dump(),
                "selection_meta": pick_meta,
            }
        )

    sel_path = ws.root / "selection.json"
    write_json(sel_path, selections)
    artifacts["selection"] = str(sel_path)
    jr.log("selection", "saved", artifacts={"path": str(sel_path), "count": len(selections)})

    # 3) bind topology + choices -> blueprint (never raise)
    bp = bind_plan_to_blueprint(plan=plan, chosen=chosen, brief=brief, entry_map=entry_map)

    bp_path = ws.root / "blueprint.json"
    write_json(bp_path, bp.model_dump())
    artifacts["blueprint"] = str(bp_path)
    jr.log("blueprint", "saved", artifacts={"path": str(bp_path), "parts": len(bp.parts), "links": len(bp.links)})

    # 4) emit DOT
    dot = blueprint_to_dot(bp)
    dot_path = ws.root / "graph.dot"
    write_text(dot_path, dot)
    artifacts["graph_dot"] = str(dot_path)
    jr.log("graph", "saved", artifacts={"path": str(dot_path)})

    # 5) emit netlist
    netlist = blueprint_to_netlist(bp)
    netlist_path = ws.root / "netlist.txt"
    write_text(netlist_path, netlist)
    artifacts["netlist"] = str(netlist_path)
    jr.log("netlist", "saved", artifacts={"path": str(netlist_path)})

    # 6) post verification (non-fatal)
    report = verify_blueprint(bp)
    report_path = ws.root / "verify_report.json"
    write_json(report_path, report.model_dump())
    artifacts["verify_report"] = str(report_path)
    jr.log("verify", "saved", artifacts={"path": str(report_path), "ok": report.ok, "issues": len(report.issues)})

    # 7) layout step 13: netlist normalization (force-output)
    layout_netlist = normalize_netlist(bp)
    layout_netlist_path = ws.root / "layout_netlist.json"
    write_json(layout_netlist_path, layout_netlist.model_dump())
    artifacts["layout_netlist"] = str(layout_netlist_path)
    jr.log("layout", "netlist_saved", artifacts={"path": str(layout_netlist_path)}, extra={"issues": len(layout_netlist.issues)})

    layout_footprints = extract_footprints(bp.parts, catalog)
    layout_footprints_path = ws.root / "layout_footprints.json"
    write_json(layout_footprints_path, layout_footprints.model_dump())
    artifacts["layout_footprints"] = str(layout_footprints_path)
    jr.log("layout", "footprints_saved", artifacts={"path": str(layout_footprints_path)}, extra={"count": len(layout_footprints.footprints)})

    layout_placements = place_instances(layout_netlist, layout_footprints)
    layout_placements_path = ws.root / "layout_placements.json"
    write_json(layout_placements_path, layout_placements.model_dump())
    artifacts["layout_placements"] = str(layout_placements_path)
    jr.log("layout", "placements_saved", artifacts={"path": str(layout_placements_path)}, extra={"count": len(layout_placements.placements)})

    layout_alignments = align_instances(layout_placements, layout_netlist, layout_footprints)
    layout_alignments_path = ws.root / "layout_alignments.json"
    write_json(layout_alignments_path, layout_alignments.model_dump())
    artifacts["layout_alignments"] = str(layout_alignments_path)
    jr.log("layout", "alignments_saved", artifacts={"path": str(layout_alignments_path)}, extra={"issues": len(layout_alignments.issues)})

    layout_routes = route_links(layout_netlist, layout_alignments)
    layout_routes_path = ws.root / "layout_routes.json"
    write_json(layout_routes_path, layout_routes.model_dump())
    artifacts["layout_routes"] = str(layout_routes_path)
    jr.log("layout", "routes_saved", artifacts={"path": str(layout_routes_path)}, extra={"count": len(layout_routes.routes), "issues": len(layout_routes.issues)})

    layout_precheck = precheck_layout(layout_alignments, layout_routes)
    layout_precheck_path = ws.root / "layout_precheck.json"
    write_json(layout_precheck_path, layout_precheck.model_dump())
    artifacts["layout_precheck"] = str(layout_precheck_path)
    jr.log("layout", "precheck_saved", artifacts={"path": str(layout_precheck_path)}, extra={"issues": len(layout_precheck.issues), "overlaps": len(layout_precheck.overlaps)})

    layout_emit = emit_gds(
        netlist=layout_netlist,
        placements=layout_alignments,
        routes=layout_routes,
        catalog_entries=catalog,
        out_dir=ws.root,
        name="layout",
    )
    layout_emit_path = ws.root / "layout_emit.json"
    write_json(layout_emit_path, layout_emit.model_dump())
    artifacts["layout_emit"] = str(layout_emit_path)
    artifacts["layout_gds"] = layout_emit.gds_path
    jr.log("layout", "emit_saved", artifacts={"path": str(layout_emit_path), "gds": layout_emit.gds_path}, extra={"issues": len(layout_emit.issues)})

    layout_report = build_layout_report(
        netlist=layout_netlist,
        footprints=layout_footprints,
        placements=layout_placements,
        alignments=layout_alignments,
        routes=layout_routes,
        precheck=layout_precheck,
        emit=layout_emit,
    )
    layout_report_path = ws.root / "layout_report.json"
    write_json(layout_report_path, layout_report.model_dump())
    artifacts["layout_report"] = str(layout_report_path)
    jr.log("layout", "report_saved", artifacts={"path": str(layout_report_path), "ok": layout_report.ok, "issues": len(layout_report.issues)})

    # 8) artifact manifest (self-contained)
    manifest_path = ws.root / "artifacts.json"
    artifacts["artifacts_manifest"] = str(manifest_path)
    write_json(manifest_path, artifacts)
    jr.log("manifest", "saved", artifacts={"path": str(manifest_path)})

    return artifacts
