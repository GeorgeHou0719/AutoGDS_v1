from __future__ import annotations

import json
import sys
from pathlib import Path


REQUIRED_FILES = [
    "artifacts.json",
    "topology_plan.json",
    "topology.dot",
    "selection.json",
    "wiring_plan.json",
    "blueprint.json",
    "graph.dot",
    "netlist.txt",
    "verify_report.json",
]

CATALOG_INDEX_REL = Path("catalog") / "index.json"


def _load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _latest_run_dir(runs_dir: Path) -> Path:
    if not runs_dir.exists() or not runs_dir.is_dir():
        raise SystemExit(f"[FAIL] runs dir not found: {runs_dir}")

    subdirs = [p for p in runs_dir.iterdir() if p.is_dir()]
    if not subdirs:
        raise SystemExit(f"[FAIL] no run directories under: {runs_dir}")

    subdirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return subdirs[0]


def _is_template_like(symbol: str, source_file: str) -> bool:
    s = (symbol or "").lower()
    f = (source_file or "").lower()
    return ("template" in s) or ("templates" in s) or ("template" in f) or ("templates" in f)


def verify_run(run_dir: Path) -> int:
    print(f"[INFO] Verifying run: {run_dir}")

    # 1) Must-have artifacts
    missing = [name for name in REQUIRED_FILES if not (run_dir / name).exists()]
    if missing:
        print("[FAIL] Missing required files:")
        for n in missing:
            print(f"  - {n}")
        return 2

    # 2) options per node should exist
    options_files = sorted(run_dir.glob("options_node_*.json"))
    if not options_files:
        print("[FAIL] No options_node_*.json found (per-node candidate lists missing).")
        return 3

    # 3) topo & selection consistency
    topo = _load_json(run_dir / "topology_plan.json")
    sel = _load_json(run_dir / "selection.json")

    nodes = topo.get("nodes", [])
    if not isinstance(nodes, list) or len(nodes) == 0:
        print("[FAIL] topology_plan.json has no nodes.")
        return 4

    if not isinstance(sel, list) or len(sel) == 0:
        print("[FAIL] selection.json is empty.")
        return 5

    node_ids = [n.get("node_id") for n in nodes if isinstance(n, dict)]
    node_ids = [x for x in node_ids if isinstance(x, str) and x]
    if len(node_ids) != len(nodes):
        print("[FAIL] topology nodes missing node_id.")
        return 6

    selected_ids = [x.get("node_id") for x in sel if isinstance(x, dict)]
    selected_ids = [x for x in selected_ids if isinstance(x, str) and x]
    missing_sel = sorted(set(node_ids) - set(selected_ids))
    if missing_sel:
        print("[FAIL] Missing selections for some topology nodes:")
        for nid in missing_sel:
            print(f"  - {nid}")
        return 7

    # 4) blueprint should cover nodes (by part name)
    bp = _load_json(run_dir / "blueprint.json")
    parts = bp.get("parts", [])
    part_names = [p.get("name") for p in parts if isinstance(p, dict)]
    part_names = [x for x in part_names if isinstance(x, str) and x]
    missing_parts = sorted(set(node_ids) - set(part_names))
    if missing_parts:
        print("[FAIL] Blueprint missing parts for some nodes:")
        for nid in missing_parts:
            print(f"  - {nid}")
        return 8

    # 5) verify_report parse check (ok may be False)
    rpt = _load_json(run_dir / "verify_report.json")
    if "ok" not in rpt or "issues" not in rpt:
        print("[FAIL] verify_report.json missing fields: ok/issues")
        return 9

    # ===== DesignLibrary / Catalog involvement checks =====
    idx_path = run_dir / CATALOG_INDEX_REL
    if not idx_path.exists():
        print(f"[FAIL] Catalog index missing: {idx_path}")
        return 10

    idx = _load_json(idx_path)
    if not isinstance(idx, list) or len(idx) == 0:
        print("[FAIL] catalog/index.json is empty or not a list.")
        return 11

    # Build lookup set from index: (symbol, source_file)
    idx_pairs = set()
    idx_template_hits = 0
    for e in idx:
        if not isinstance(e, dict):
            continue
        sym = str(e.get("symbol", "") or "")
        src = str(e.get("source_file", "") or "")
        idx_pairs.add((sym, src))
        if _is_template_like(sym, src):
            idx_template_hits += 1

    # Check options are mostly from index and contain no templates
    opt_total = 0
    opt_in_index = 0
    opt_template_hits = 0

    for fp in options_files:
        arr = _load_json(fp)
        if not isinstance(arr, list):
            continue
        for o in arr:
            if not isinstance(o, dict):
                continue
            sym = str(o.get("symbol", "") or "")
            src = str(o.get("source_file", "") or "")
            opt_total += 1
            if (sym, src) in idx_pairs:
                opt_in_index += 1
            if _is_template_like(sym, src):
                opt_template_hits += 1

    # Check selection are from index and contain no templates
    sel_total = 0
    sel_in_index = 0
    sel_template_hits = 0
    unbound = 0

    for x in sel:
        if not isinstance(x, dict):
            continue
        picked = x.get("selected", {})
        if not isinstance(picked, dict):
            continue
        sym = str(picked.get("symbol", "") or "")
        src = str(picked.get("source_file", "") or "")
        if sym == "(unbound)":
            unbound += 1
        sel_total += 1
        if (sym, src) in idx_pairs:
            sel_in_index += 1
        if _is_template_like(sym, src):
            sel_template_hits += 1

    # Print summary (hard fail only on template violations; index-hit is soft gate)
    print("[PASS] Pipeline artifacts exist and are consistent.")
    print(f"[INFO] Nodes: {len(nodes)} | Options files: {len(options_files)} | verify.ok={rpt.get('ok')} | issues={len(rpt.get('issues', [])) if isinstance(rpt.get('issues'), list) else 'NA'}")

    print(f"[INFO] Catalog index entries: {len(idx_pairs)} | index template-like entries: {idx_template_hits}")
    print(f"[INFO] Options: total={opt_total}, in_index={opt_in_index}, hit_rate={(opt_in_index/opt_total if opt_total else 0):.2%}, template_hits={opt_template_hits}")
    print(f"[INFO] Selection: total={sel_total}, in_index={sel_in_index}, hit_rate={(sel_in_index/sel_total if sel_total else 0):.2%}, template_hits={sel_template_hits}, unbound={unbound}")

    if idx_template_hits > 0 or opt_template_hits > 0 or sel_template_hits > 0:
        print("[FAIL] components-only violation: found template-like entries in index/options/selection.")
        return 12

    # Soft expectation: selection hit-rate should be high (but not a hard fail because fallback is allowed)
    if sel_total > 0 and (sel_in_index / sel_total) < 0.8:
        print("[WARN] Low selection-in-index hit rate (<80%). This suggests heavy fallback or mismatched catalog root.")
        print("       Pipeline still passes because forced output is allowed, but catalog involvement is weak.")

    return 0


def main() -> int:
    repo_root = Path.cwd()
    if len(sys.argv) >= 2:
        run_dir = Path(sys.argv[1]).expanduser().resolve()
    else:
        run_dir = _latest_run_dir(repo_root / "runs")
    return verify_run(run_dir)


if __name__ == "__main__":
    raise SystemExit(main())
