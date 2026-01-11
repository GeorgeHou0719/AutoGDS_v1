from __future__ import annotations

import re
from typing import Dict, List, Tuple

from autogds.layout_schema import LayoutRoutes, Route, LayoutPlacements, LayoutNetlist


def _center(pl) -> Dict[str, float]:
    return {
        "x": pl.x_um + pl.width_um / 2,
        "y": pl.y_um + pl.height_um / 2,
    }


def _box(pl) -> Tuple[float, float, float, float]:
    return (pl.x_um, pl.y_um, pl.x_um + pl.width_um, pl.y_um + pl.height_um)


def _segment_hits_box(seg: Tuple[Dict[str, float], Dict[str, float]], box: Tuple[float, float, float, float]) -> bool:
    (x1, y1), (x2, y2) = (seg[0]["x"], seg[0]["y"]), (seg[1]["x"], seg[1]["y"])
    left, top, right, bottom = box[0], box[1], box[2], box[3]

    if x1 == x2:
        x = x1
        if left <= x <= right:
            y_min, y_max = sorted([y1, y2])
            return y_min <= bottom and y_max >= top
        return False

    if y1 == y2:
        y = y1
        if top <= y <= bottom:
            x_min, x_max = sorted([x1, x2])
            return x_min <= right and x_max >= left
        return False

    return False


def _path_hits_any(path: List[Dict[str, float]], boxes: List[Tuple[float, float, float, float]]) -> bool:
    for i in range(len(path) - 1):
        seg = (path[i], path[i + 1])
        for box in boxes:
            if _segment_hits_box(seg, box):
                return True
    return False


def route_links(
    netlist: LayoutNetlist,
    placements: LayoutPlacements,
) -> LayoutRoutes:
    pl_map: Dict[str, object] = {p.name: p for p in placements.placements}
    routes: List[Route] = []
    issues: List[str] = []
    link_groups: Dict[str, List[object]] = {}

    for lk in netlist.links:
        link_groups.setdefault(lk.a, []).append(lk)

    remap_ports: Dict[Tuple[str, str, str], str] = {}
    for src, links in link_groups.items():
        if len(links) < 2:
            continue
        prefixes = []
        ports = []
        for lk in links:
            m = re.match(r"^([a-zA-Z_]+)(\d+)$", lk.a_port)
            if not m:
                break
            prefixes.append(m.group(1))
            ports.append((lk.a_port, int(m.group(2))))
        else:
            if len(set(prefixes)) != 1:
                continue
            ports = sorted(set(ports), key=lambda p: p[1])
            targets = []
            for lk in links:
                b_pl = pl_map.get(lk.b)
                if not b_pl:
                    continue
                targets.append((lk, _center(b_pl)["y"]))
            if len(targets) < 2 or len(ports) != len(targets):
                continue

            targets.sort(key=lambda t: t[1], reverse=True)
            for idx, (lk, _y) in enumerate(targets):
                remap_ports[(lk.a, lk.b, lk.b_port)] = ports[idx][0]
            continue

    for i, lk in enumerate(netlist.links):
        a_pl = pl_map.get(lk.a)
        b_pl = pl_map.get(lk.b)
        if not a_pl or not b_pl:
            issues.append(f"missing_placement:{lk.a}->{lk.b}")
            routes.append(
                Route(
                    link_id=f"l{i}",
                    a=lk.a,
                    a_port=lk.a_port,
                    b=lk.b,
                    b_port=lk.b_port,
                    points=[],
                    issues=["missing_placement"],
                )
            )
            continue

        a_port = remap_ports.get((lk.a, lk.b, lk.b_port), lk.a_port)
        a = _center(a_pl)
        b = _center(b_pl)
        other_boxes = []
        for name, pl in pl_map.items():
            if name in {lk.a, lk.b}:
                continue
            other_boxes.append(_box(pl))

        mid_h = {"x": b["x"], "y": a["y"]}
        path_h = [a, mid_h, b]
        mid_v = {"x": a["x"], "y": b["y"]}
        path_v = [a, mid_v, b]

        if _path_hits_any(path_h, other_boxes) and not _path_hits_any(path_v, other_boxes):
            points = path_v
        else:
            points = path_h
        routes.append(
            Route(
                link_id=f"l{i}",
                a=lk.a,
                a_port=a_port,
                b=lk.b,
                b_port=lk.b_port,
                points=points,
                issues=[],
            )
        )

    return LayoutRoutes(routes=routes, issues=issues)
