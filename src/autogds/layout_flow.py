from __future__ import annotations

from typing import Dict, List

import re

from autogds.layout_schema import LayoutNetlist, NetlistInstance, NetlistLink
from autogds.schema import Blueprint


def normalize_netlist(bp: Blueprint) -> LayoutNetlist:
    instances: List[NetlistInstance] = []
    links: List[NetlistLink] = []
    issues: List[str] = []

    for part in bp.parts:
        instances.append(
            NetlistInstance(
                name=part.name,
                symbol=part.symbol,
                params=dict(part.params or {}),
            )
        )
        if part.symbol == "(unbound)":
            issues.append(f"unbound_part:{part.name}")
        for msg in part.param_issues or []:
            issues.append(f"param_issue:{part.name}:{msg}")
        for msg in part.port_map_issues or []:
            issues.append(f"port_map_issue:{part.name}:{msg}")

    for lk in bp.links:
        links.append(NetlistLink(a=lk.a, a_port=lk.a_port, b=lk.b, b_port=lk.b_port))

    if not instances:
        issues.append("no_instances")

    hint = None
    if instances:
        mesh_names = [inst.name for inst in instances if re.match(r"^n\d+_\d+$", inst.name)]
        if len(mesh_names) == len(instances) and len(mesh_names) >= 4:
            rows = set()
            cols = set()
            for name in mesh_names:
                m = re.match(r"^n(\d+)_([0-9]+)$", name)
                if not m:
                    break
                rows.add(int(m.group(1)))
                cols.add(int(m.group(2)))
            else:
                if len(rows) > 1 and len(cols) > 1:
                    hint = "grid"
    if hint is None and bp.parts and not bp.links:
        hint = "y_array"
    return LayoutNetlist(
        instances=instances,
        links=links,
        top_ports=dict(bp.top_ports or {}),
        layout_hint=hint,
        issues=issues,
    )
