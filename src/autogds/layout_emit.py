from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
import sys
from typing import Dict, List

from autogds.layout_schema import LayoutEmit, LayoutNetlist, LayoutPlacements, LayoutRoutes
from autogds.workspace import write_text


def _load_module_from_path(path: Path):
    _ensure_repo_on_syspath(path)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _ensure_repo_on_syspath(path: Path) -> None:
    try:
        parts = list(path.resolve().parents)
        repo_root = None
        for p in parts:
            if p.name.lower() == "knowledgebase":
                repo_root = p.parent
                break
        if repo_root is None:
            repo_root = path.resolve().parents[2]
        repo_root_str = str(repo_root)
        if repo_root_str not in sys.path:
            sys.path.insert(0, repo_root_str)
    except Exception:
        return


def _get_symbol_parts(symbol: str) -> tuple[str, str | None]:
    if ":" in symbol:
        mod, fn = symbol.split(":", 1)
        return mod, fn
    return symbol, None


def _safe_call_component(func, params: Dict[str, object]):
    try:
        sig = inspect.signature(func)
        allowed = {k: v for k, v in params.items() if k in sig.parameters}
        return func(**allowed), None
    except Exception as e:
        return None, str(e)


def emit_gds(
    netlist: LayoutNetlist,
    placements: LayoutPlacements,
    routes: LayoutRoutes,
    catalog_entries: List[object],
    out_dir: Path,
    name: str = "layout",
) -> LayoutEmit:
    issues: List[str] = []
    out_dir = Path(out_dir)
    gds_path = out_dir / f"{name}.gds"

    try:
        import gdsfactory as gf  # optional dependency
    except Exception as e:
        issues.append(f"gdsfactory_missing:{e}")
        _write_placeholder(gds_path)
        return LayoutEmit(gds_path=str(gds_path), issues=issues)

    pdk_issue = _activate_autogds_pdk(gf, catalog_entries)
    if pdk_issue:
        issues.append(pdk_issue)


    sym_to_entry = {c.symbol: c for c in catalog_entries}
    inst_map = {inst.name: inst for inst in netlist.instances}
    pl_map = {pl.name: pl for pl in placements.placements}

    top = gf.Component()
    refs: Dict[str, object] = {}

    for name_key, inst in inst_map.items():
        pl = pl_map.get(name_key)
        entry = sym_to_entry.get(inst.symbol)
        if not pl or not entry:
            issues.append(f"missing_instance_or_placement:{name_key}")
            continue

        mod = _load_module_from_path(Path(entry.source_file))
        if mod is None:
            issues.append(f"module_load_failed:{entry.source_file}")
            continue

        _mod_name, fn_name = _get_symbol_parts(inst.symbol)
        func = None
        if fn_name and hasattr(mod, fn_name):
            func = getattr(mod, fn_name)
        elif hasattr(mod, entry.symbol):
            func = getattr(mod, entry.symbol)
        else:
            # fallback: try module-level function with same stem
            if hasattr(mod, Path(entry.source_file).stem):
                func = getattr(mod, Path(entry.source_file).stem)

        if not callable(func):
            issues.append(f"component_not_callable:{inst.symbol}")
            continue

        params = dict(inst.params or {})
        params.pop("role", None)
        comp, err = _safe_call_component(func, params)
        if comp is None:
            issues.append(f"component_call_failed:{inst.symbol}:{err}")
            continue

        ref = top << comp
        if pl.rotation_deg:
            ref.rotate(pl.rotation_deg)
        ref.move((pl.x_um, pl.y_um))
        refs[name_key] = ref

    pair_port_map: Dict[tuple, Dict[str, str]] = {}
    group_map: Dict[tuple, List[LayoutRoutes]] = {}
    for r in routes.routes:
        group_map.setdefault((r.a, r.b), []).append(r)
    for (a_name, b_name), group in group_map.items():
        if len(group) < 2:
            continue
        a_ref = refs.get(a_name)
        b_ref = refs.get(b_name)
        if not a_ref or not b_ref:
            continue
        a_ports = [r.a_port for r in group if r.a_port in a_ref.ports]
        b_ports = [r.b_port for r in group if r.b_port in b_ref.ports]
        a_ports = list(dict.fromkeys(a_ports))
        b_ports = list(dict.fromkeys(b_ports))
        if len(a_ports) != len(b_ports) or len(a_ports) < 2:
            continue
        a_sorted = sorted(a_ports, key=lambda p: a_ref.ports[p].center[1], reverse=True)
        b_sorted = sorted(b_ports, key=lambda p: b_ref.ports[p].center[1], reverse=True)
        pair_port_map[(a_name, b_name)] = {a: b for a, b in zip(a_sorted, b_sorted)}

    start_straight_overrides: Dict[str, float] = {}
    port_groups: List[List[dict]] = []
    x_group_tol = 2.0
    y_group_tol = 10.0
    step = 2.0
    a_port_overrides: Dict[str, str] = {}

    for r in routes.routes:
        a_ref = refs.get(r.a)
        b_ref = refs.get(r.b)
        if not a_ref or not b_ref:
            continue
        if r.a_port not in a_ref.ports or r.b_port not in b_ref.ports:
            continue
        a_port = a_ref.ports[r.a_port]
        b_port = b_ref.ports[r.b_port]
        item = {
            "link_id": r.link_id,
            "a_x": float(a_port.center[0]),
            "a_y": float(a_port.center[1]),
            "b_x": float(b_port.center[0]),
            "b_y": float(b_port.center[1]),
        }
        placed = False
        for group in port_groups:
            ref_x = group[0]["a_x"]
            if abs(item["a_x"] - ref_x) <= x_group_tol:
                group.append(item)
                placed = True
                break
        if not placed:
            port_groups.append([item])

    for group in port_groups:
        if len(group) < 2:
            continue
        group.sort(key=lambda item: item["a_y"])
        subgroups: List[List[dict]] = []
        current: List[dict] = [group[0]]
        for item in group[1:]:
            if abs(item["a_y"] - current[-1]["a_y"]) <= y_group_tol:
                current.append(item)
            else:
                subgroups.append(current)
                current = [item]
        subgroups.append(current)

        for subgroup in subgroups:
            if len(subgroup) < 2:
                continue
            directions = []
            for item in subgroup:
                if item["b_y"] > item["a_y"] + 1e-6:
                    directions.append(1)
                elif item["b_y"] < item["a_y"] - 1e-6:
                    directions.append(-1)
                else:
                    directions.append(0)

            all_up = all(d > 0 for d in directions)
            all_down = all(d < 0 for d in directions)
            if not (all_up or all_down):
                continue

            if all_up:
                ordered = sorted(subgroup, key=lambda item: item["a_y"], reverse=True)
            else:
                ordered = sorted(subgroup, key=lambda item: item["a_y"])

            for idx, item in enumerate(ordered):
                start_straight_overrides[item["link_id"]] = idx * step

    outgoing_map: Dict[str, List[LayoutRoutes]] = {}
    for r in routes.routes:
        outgoing_map.setdefault(r.a, []).append(r)

    for a_name, links in outgoing_map.items():
        if len(links) < 2:
            continue
        a_ref = refs.get(a_name)
        if not a_ref:
            continue
        a_ports = [r.a_port for r in links if r.a_port in a_ref.ports]
        a_ports = list(dict.fromkeys(a_ports))
        if len(a_ports) != len(links) or len(a_ports) < 2:
            continue
        a_sorted = sorted(a_ports, key=lambda p: a_ref.ports[p].center[1], reverse=True)

        def _target_y(link: LayoutRoutes) -> float:
            b_ref = refs.get(link.b)
            if b_ref and link.b_port in b_ref.ports:
                return float(b_ref.ports[link.b_port].center[1])
            return float(pl_map.get(link.b).y_um) if pl_map.get(link.b) else 0.0

        links_sorted = sorted(links, key=_target_y, reverse=True)
        for idx, link in enumerate(links_sorted):
            a_port_overrides[link.link_id] = a_sorted[idx]

    # Best-effort routing using gdsfactory if ports are available
    for r in routes.routes:
        a_ref = refs.get(r.a)
        b_ref = refs.get(r.b)
        if not a_ref or not b_ref:
            issues.append(f"route_missing_ref:{r.link_id}")
            continue
        a_port_name = a_port_overrides.get(r.link_id, r.a_port)
        b_port_name = r.b_port
        mapped = pair_port_map.get((r.a, r.b))
        if mapped and a_port_name in mapped:
            b_port_name = mapped[a_port_name]

        if a_port_name not in a_ref.ports or b_port_name not in b_ref.ports:
            issues.append(f"route_missing_port:{r.link_id}")
            continue
        try:
            a_port = a_ref.ports[a_port_name]
            b_port = b_ref.ports[b_port_name]
            start_straight = start_straight_overrides.get(r.link_id)

            if hasattr(gf.routing, "get_route"):
                kwargs = {"cross_section": "strip", "bend": "bend_euler"}
                if start_straight is not None:
                    sig = inspect.signature(gf.routing.get_route)
                    if "start_straight_length" in sig.parameters:
                        kwargs["start_straight_length"] = start_straight
                route = gf.routing.get_route(
                    a_port,
                    b_port,
                    **kwargs,
                )
                top.add(route.references)
            else:
                kwargs = {"cross_section": "strip", "bend": "bend_euler"}
                if start_straight is not None:
                    kwargs["start_straight_length"] = start_straight
                gf.routing.route_single(
                    top,
                    a_port,
                    b_port,
                    **kwargs,
                )
        except Exception as e:
            issues.append(f"route_failed:{r.link_id}:{e}")

    try:
        top.write_gds(str(gds_path))
    except Exception as e:
        issues.append(f"gds_write_failed:{e}")
        _write_placeholder(gds_path)

    return LayoutEmit(gds_path=str(gds_path), issues=issues)


def _write_placeholder(path: Path) -> None:
    try:
        write_text(
            path,
            "# Placeholder GDS file\n"
            "# Layout emit fallback; gdsfactory unavailable or failed.\n",
        )
    except Exception:
        pass


def _ports_by_orientation(ref, orientation: int) -> List[str]:
    ports = []
    port_objs = []
    if hasattr(ref.ports, "values"):
        port_objs = list(ref.ports.values())
    elif hasattr(ref.ports, "items"):
        port_objs = [p for _name, p in ref.ports.items()]
    else:
        try:
            port_objs = list(ref.ports)
        except Exception:
            port_objs = []

    for p in port_objs:
        if int(p.orientation) == orientation:
            ports.append(p)
    ports.sort(key=lambda p: p.y, reverse=True)
    return [p.name for p in ports]


def _activate_autogds_pdk(gf, catalog_entries: List[object]) -> str | None:
    try:
        from gdsfactory.generic_tech import get_generic_pdk
    except Exception as e:
        return f"pdk_generic_missing:{e}"

    try:
        generic = get_generic_pdk()
        cells: Dict[str, object] = dict(generic.cells or {})
        for entry in catalog_entries:
            mod = _load_module_from_path(Path(entry.source_file))
            if mod is None:
                continue
            _mod_name, fn_name = _get_symbol_parts(entry.symbol)
            func = None
            if fn_name and hasattr(mod, fn_name):
                func = getattr(mod, fn_name)
            elif hasattr(mod, entry.symbol):
                func = getattr(mod, entry.symbol)
            else:
                stem = Path(entry.source_file).stem
                if hasattr(mod, stem):
                    func = getattr(mod, stem)
            if callable(func):
                cell_name = func.__name__
                if cell_name not in cells:
                    cells[cell_name] = func
                if cell_name.startswith("_"):
                    alias = cell_name.lstrip("_")
                    if alias and alias not in cells:
                        cells[alias] = func

        pdk = gf.Pdk(
            name="AutoGDSPDK",
            layers=generic.layers,
            cross_sections=generic.cross_sections,
            cells=cells,
            layer_views=generic.layer_views,
        )
        pdk.activate()
        return None
    except Exception as e:
        return f"pdk_activate_failed:{e}"
