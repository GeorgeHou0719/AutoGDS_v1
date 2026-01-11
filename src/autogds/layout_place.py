from __future__ import annotations

import re
from typing import Dict, List, Tuple

from autogds.layout_schema import LayoutPlacements, Placement, LayoutFootprints, LayoutNetlist


def _build_tree_order_map(netlist: LayoutNetlist) -> Dict[str, int] | None:
    inst_names = [inst.name for inst in netlist.instances]
    if not inst_names or not netlist.links:
        return None

    incoming: Dict[str, int] = {name: 0 for name in inst_names}
    outgoing: Dict[str, List[Tuple[str, str]]] = {name: [] for name in inst_names}
    for lk in netlist.links:
        if lk.a in outgoing and lk.b in incoming:
            outgoing[lk.a].append((lk.a_port or "", lk.b))
            incoming[lk.b] += 1

    roots = [name for name, count in incoming.items() if count == 0]
    if len(roots) != 1:
        return None

    for name in inst_names:
        if incoming[name] > 1 or len(outgoing[name]) > 2:
            return None

    def _port_order(port: str) -> int:
        m = re.search(r"(\d+)$", port)
        return int(m.group(1)) if m else 0

    order_map: Dict[str, int] = {roots[0]: 0}
    queue: List[str] = [roots[0]]
    while queue:
        parent = queue.pop(0)
        children = outgoing.get(parent, [])
        if not children:
            continue
        children_sorted = sorted(children, key=lambda item: _port_order(item[0]))
        for idx, (_aport, child) in enumerate(children_sorted):
            if child not in order_map:
                order_map[child] = order_map[parent] * 2 + idx
                queue.append(child)

    if len(order_map) != len(inst_names):
        return None
    return order_map


def place_instances(
    netlist: LayoutNetlist,
    footprints: LayoutFootprints,
    spacing_um: float = 40.0,
) -> LayoutPlacements:
    fp_map: Dict[str, object] = {fp.name: fp for fp in footprints.footprints}

    placements: List[Placement] = []
    issues: List[str] = []

    inst_names = [inst.name for inst in netlist.instances]
    incoming: Dict[str, int] = {name: 0 for name in inst_names}
    outgoing: Dict[str, List[str]] = {name: [] for name in inst_names}

    for lk in netlist.links:
        if lk.a in outgoing and lk.b in incoming:
            outgoing[lk.a].append(lk.b)
            incoming[lk.b] += 1

    if inst_names and netlist.links:
        adjacency: Dict[str, List[str]] = {name: [] for name in inst_names}
        for lk in netlist.links:
            adjacency[lk.a].append(lk.b)
            adjacency[lk.b].append(lk.a)

        visited = set()
        components: List[List[str]] = []
        for name in inst_names:
            if name in visited:
                continue
            queue = [name]
            comp = []
            visited.add(name)
            while queue:
                cur = queue.pop(0)
                comp.append(cur)
                for nxt in adjacency.get(cur, []):
                    if nxt not in visited:
                        visited.add(nxt)
                        queue.append(nxt)
            components.append(comp)

        if components and all(len(c) == 2 for c in components):
            comp_links = []
            for comp in components:
                a_name, b_name = comp
                link = next(
                    (lk for lk in netlist.links if {lk.a, lk.b} == {a_name, b_name}),
                    None,
                )
                if link is None:
                    break
                comp_links.append((a_name, b_name, link))
            else:
                sizes: Dict[str, Tuple[float, float]] = {}
                for name in inst_names:
                    fp = fp_map.get(name)
                    if fp:
                        width = fp.width_um
                        height = fp.height_um
                    else:
                        width = 50.0
                        height = 20.0
                        issues.append(f"missing_footprint:{name}")
                    sizes[name] = (width, height)

                comp_heights = []
                for a_name, b_name, link in comp_links:
                    a = link.a
                    b = link.b
                    comp_heights.append(max(sizes[a][1], sizes[b][1]))

                total_height = sum(comp_heights) + spacing_um * max(0, len(comp_heights) - 1)
                y = -total_height / 2.0
                for (a_name, b_name, link), comp_h in zip(comp_links, comp_heights):
                    left = link.a
                    right = link.b
                    left_inst = next(i for i in netlist.instances if i.name == left)
                    right_inst = next(i for i in netlist.instances if i.name == right)
                    left_role = (left_inst.params or {}).get("role", "")
                    right_role = (right_inst.params or {}).get("role", "")
                    if left_role == "grating_coupler" and right_role != "grating_coupler":
                        left, right = right, left
                        left_inst, right_inst = right_inst, left_inst
                    left_w = sizes[left][0]
                    placements.append(
                        Placement(
                            name=left,
                            symbol=left_inst.symbol,
                            x_um=0.0,
                            y_um=y,
                            rotation_deg=0.0,
                            width_um=sizes[left][0],
                            height_um=sizes[left][1],
                            issues=[],
                        )
                    )
                    placements.append(
                        Placement(
                            name=right,
                            symbol=right_inst.symbol,
                            x_um=left_w + spacing_um,
                            y_um=y,
                            rotation_deg=0.0,
                            width_um=sizes[right][0],
                            height_um=sizes[right][1],
                            issues=[],
                        )
                    )
                    y += comp_h + spacing_um
                return LayoutPlacements(placements=placements, issues=issues)

    if netlist.layout_hint == "y_array" and inst_names:
        sizes: Dict[str, Tuple[float, float]] = {}
        for name in inst_names:
            fp = fp_map.get(name)
            if fp:
                width = fp.width_um
                height = fp.height_um
            else:
                width = 50.0
                height = 20.0
                issues.append(f"missing_footprint:{name}")
            sizes[name] = (width, height)

        max_width = max((sizes[n][0] for n in inst_names), default=50.0)
        total_height = sum(sizes[n][1] for n in inst_names) + spacing_um * max(0, len(inst_names) - 1)
        y = -total_height / 2.0
        x = 0.0
        for name in inst_names:
            width, height = sizes[name]
            inst = next(i for i in netlist.instances if i.name == name)
            placements.append(
                Placement(
                    name=inst.name,
                    symbol=inst.symbol,
                    x_um=x,
                    y_um=y,
                    rotation_deg=0.0,
                    width_um=width,
                    height_um=height,
                    issues=[],
                )
            )
            y += height + spacing_um
        return LayoutPlacements(placements=placements, issues=issues)

    if netlist.layout_hint == "grid" and inst_names:
        coords: Dict[str, Tuple[int, int]] = {}
        for name in inst_names:
            m = re.match(r"^n(\d+)_([0-9]+)$", name)
            if not m:
                break
            coords[name] = (int(m.group(1)), int(m.group(2)))
        if len(coords) == len(inst_names):
            sizes: Dict[str, Tuple[float, float]] = {}
            for name in inst_names:
                fp = fp_map.get(name)
                if fp:
                    width = fp.width_um
                    height = fp.height_um
                else:
                    width = 50.0
                    height = 20.0
                    issues.append(f"missing_footprint:{name}")
                sizes[name] = (width, height)

            max_width = max((sizes[n][0] for n in inst_names), default=50.0)
            max_height = max((sizes[n][1] for n in inst_names), default=20.0)
            max_row = max(r for r, _c in coords.values())
            max_col = max(c for _r, c in coords.values())
            x_pitch = max_width + spacing_um
            y_pitch = max_height + spacing_um

            for name in inst_names:
                r, c = coords[name]
                inst = next(i for i in netlist.instances if i.name == name)
                x = c * x_pitch
                y = (max_row - r) * y_pitch
                width, height = sizes[name]
                placements.append(
                    Placement(
                        name=inst.name,
                        symbol=inst.symbol,
                        x_um=x,
                        y_um=y,
                        rotation_deg=0.0,
                        width_um=width,
                        height_um=height,
                        issues=[],
                    )
                )
            return LayoutPlacements(placements=placements, issues=issues)

    roots = [name for name, count in incoming.items() if count == 0]
    if not roots and inst_names:
        roots = [inst_names[0]]

    layers: Dict[str, int] = {}
    queue: List[Tuple[str, int]] = [(r, 0) for r in roots]
    while queue:
        name, layer = queue.pop(0)
        prev = layers.get(name, -1)
        if layer <= prev:
            continue
        layers[name] = layer
        for child in outgoing.get(name, []):
            queue.append((child, layer + 1))

    for name in inst_names:
        layers.setdefault(name, 0)

    layer_to_insts: Dict[int, List[str]] = {}
    for name, layer in layers.items():
        layer_to_insts.setdefault(layer, []).append(name)

    tree_order = _build_tree_order_map(netlist)

    x = 0.0
    for layer in sorted(layer_to_insts.keys()):
        names = sorted(layer_to_insts[layer])
        if tree_order and all(n in tree_order for n in names):
            names = sorted(names, key=lambda n: tree_order[n], reverse=True)
        sizes: Dict[str, Tuple[float, float]] = {}
        for name in names:
            fp = fp_map.get(name)
            if fp:
                width = fp.width_um
                height = fp.height_um
            else:
                width = 50.0
                height = 20.0
                issues.append(f"missing_footprint:{name}")
            sizes[name] = (width, height)

        layer_width = max((sizes[n][0] for n in names), default=50.0)
        total_height = sum(sizes[n][1] for n in names) + spacing_um * max(0, len(names) - 1)
        y = -total_height / 2.0

        for name in names:
            width, height = sizes[name]
            inst = next(i for i in netlist.instances if i.name == name)
            placements.append(
                Placement(
                    name=inst.name,
                    symbol=inst.symbol,
                    x_um=x,
                    y_um=y,
                    rotation_deg=0.0,
                    width_um=width,
                    height_um=height,
                    issues=[],
                )
            )
            y += height + spacing_um

        x += layer_width + spacing_um

    return LayoutPlacements(placements=placements, issues=issues)
