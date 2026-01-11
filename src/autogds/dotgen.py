from __future__ import annotations

from autogds.schema import Blueprint


def blueprint_to_dot(bp: Blueprint) -> str:
    lines = []
    lines.append("digraph AutoGDS {")
    lines.append('  rankdir="LR";')
    lines.append('  node [shape=box];')

    for p in bp.parts:
        label = f"{p.name}\\n{p.symbol}"
        lines.append(f'  "{p.name}" [label="{label}"];')

    for link in bp.links:
        elabel = f"{link.a_port} -> {link.b_port}"
        lines.append(f'  "{link.a}" -> "{link.b}" [label="{elabel}"];')

    # top ports (optional visualization)
    if bp.top_ports:
        lines.append('  node [shape=diamond];')
        for port_name, m in bp.top_ports.items():
            lines.append(f'  "{port_name}" [label="{port_name}"];')
            part = m.get("part")
            port = m.get("port")
            if part and port:
                lines.append(f'  "{port_name}" -> "{part}" [label="{port}"];')

    lines.append("}")
    return "\n".join(lines)
