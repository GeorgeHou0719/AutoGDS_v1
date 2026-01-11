from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from autogds.schema import Blueprint, Link, Part


class AssembleError(RuntimeError):
    pass


@dataclass(frozen=True)
class PickedBlock:
    block_index: int
    role_raw: str
    role_canonical: str
    symbol: str


def _slug(s: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in s.lower()).strip("_")


def assemble_blueprint(selected_blocks: List[PickedBlock]) -> Blueprint:
    """
    Assemble a Blueprint from picked blocks using simple topology templates.
    Current version:
      - MZI template (requires: 2x coupler_2x2, 1x phase_shifter, and optionally an 'arm' primitive)
    Fallback:
      - If no template matches, produce a serial chain (previous behavior).
    """
    # Group by canonical role
    by_role: Dict[str, List[PickedBlock]] = {}
    for b in selected_blocks:
        by_role.setdefault(b.role_canonical, []).append(b)

    # --- Template: MZI (minimal)
    # Requirements (strict, because you chose not to auto-fix):
    #   - at least 2 couplers
    #   - at least 1 phase shifter
    couplers = by_role.get("coupler_2x2", [])
    shifters = by_role.get("phase_shifter", [])
    arms = by_role.get("mzi_arm", []) or by_role.get("interconnect", [])  # if you later allow it

    wants_mzi = ("mzi_2x2" in by_role) or (len(couplers) + len(shifters) >= 2 and "mzi" in " ".join([b.role_raw for b in selected_blocks]).lower())

    if wants_mzi:
        if len(couplers) < 2:
            raise AssembleError(f"MZI assembly requires 2 couplers (coupler_2x2), got {len(couplers)}.")
        if len(shifters) < 1:
            raise AssembleError("MZI assembly requires 1 phase shifter (phase_shifter), got 0.")

        # Pick first two couplers and first shifter
        c0, c1 = couplers[0], couplers[1]
        ps = shifters[0]

        # Parts
        p_c0 = Part(name=f"b{c0.block_index}_{_slug(c0.role_canonical)}_a", symbol=c0.symbol, params={})
        p_c1 = Part(name=f"b{c1.block_index}_{_slug(c1.role_canonical)}_b", symbol=c1.symbol, params={})
        p_ps = Part(name=f"b{ps.block_index}_{_slug(ps.role_canonical)}", symbol=ps.symbol, params={})

        parts = [p_c0, p_c1, p_ps]

        # Links (assume 2x2 coupler has ports: in0,in1,out0,out1 ; shifter: in0,out0)
        # Arm0: c0.out0 -> ps.in0 -> c1.in0
        # Arm1: c0.out1 -> c1.in1 (direct)
        links = [
            Link(a=p_c0.name, a_port="out0", b=p_ps.name, b_port="in0"),
            Link(a=p_ps.name, a_port="out0", b=p_c1.name, b_port="in0"),
            Link(a=p_c0.name, a_port="out1", b=p_c1.name, b_port="in1"),
        ]

        top_ports = {
            "in0": {"part": p_c0.name, "port": "in0"},
            "in1": {"part": p_c0.name, "port": "in1"},
            "out0": {"part": p_c1.name, "port": "out0"},
            "out1": {"part": p_c1.name, "port": "out1"},
        }

        return Blueprint(parts=parts, links=links, top_ports=top_ports)

    # --- Fallback: serial chain (your Step5 behavior)
    parts: List[Part] = []
    for b in selected_blocks:
        parts.append(Part(name=f"b{b.block_index}_{_slug(b.role_canonical)}", symbol=b.symbol, params={}))

    links: List[Link] = []
    for i in range(len(parts) - 1):
        links.append(Link(a=parts[i].name, a_port="out0", b=parts[i + 1].name, b_port="in0"))

    top_ports = {}
    if parts:
        top_ports["in0"] = {"part": parts[0].name, "port": "in0"}
        top_ports["out0"] = {"part": parts[-1].name, "port": "out0"}

    return Blueprint(parts=parts, links=links, top_ports=top_ports)
