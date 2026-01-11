from __future__ import annotations

from autogds.schema import Blueprint


def blueprint_to_netlist(bp: Blueprint) -> str:
    lines = ["# AutoGDS Netlist r1", ""]

    for p in bp.parts:
        lines.append(f".part {p.name} {p.symbol}")
        for k, v in (p.params or {}).items():
            lines.append(f".param {p.name}.{k} {v}")
        lines.append("")

    for i, lk in enumerate(bp.links):
        net = f"n{i}"
        lines.append(f".net {net} {lk.a}.{lk.a_port} {lk.b}.{lk.b_port}")

    for tp, ref in bp.top_ports.items():
        lines.append(f".top {tp} {ref.get('part','')}.{ref.get('port','')}")

    lines.append("")
    lines.append(".end")
    return "\n".join(lines) + "\n"
