from __future__ import annotations

import re
from typing import List, Dict, Optional, Tuple
from autogds.schema import DesignBrief, TopologyPlan, TopologyNode, TopologyIntent
from autogds.role_vocab import normalize_role


_PORT_FORM_RE = re.compile(r"\b(\d+)\s*[xX]\s*(\d+)\b")
_IN_RE = re.compile(r"\b(\d+)\s*[- ]*(input|inputs|in)\b")
_OUT_RE = re.compile(r"\b(\d+)\s*[- ]*(output|outputs|out)\b")
_CHANNEL_RE = re.compile(r"\b(\d+)\s*(channel|channels)\b")
_COMMON_RE = re.compile(r"\b(\d+)\s*(common|bus)\b")
_PORT_PAIR_RE = re.compile(
    r"\bport\s*(\d+)\b[^.]{0,80}?\bto\b[^.]{0,80}?\bport\s*(\d+)\b"
)
_PORT_PAIR_IO_RE = re.compile(
    r"\boutput\s*port\s*(\d+)\b[^.]{0,80}?\bto\b[^.]{0,80}?\binput\s*port\s*(\d+)\b"
)

_WORD_NUMS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
}


def _word_num_to_int(text: str) -> Optional[int]:
    t = (text or "").lower().strip()
    return _WORD_NUMS.get(t)


def _parse_port_requirements(text: str) -> Tuple[Optional[str], Dict[str, int]]:
    if not text:
        return None, {}

    text = (
        text.replace("×", "x")
        .replace("‑", "-")
        .replace("–", "-")
        .replace("—", "-")
    )

    port_form = None
    required: Dict[str, int] = {}

    m = _PORT_FORM_RE.search(text)
    if m:
        try:
            in_n = int(m.group(1))
            out_n = int(m.group(2))
            port_form = f"{in_n}x{out_n}"
            required = {"in": in_n, "out": out_n}
            return port_form, required
        except Exception:
            pass

    in_match = _IN_RE.search(text)
    out_match = _OUT_RE.search(text)
    if in_match:
        required["in"] = int(in_match.group(1))
    if out_match:
        required["out"] = int(out_match.group(1))

    if "in" not in required:
        for word, val in _WORD_NUMS.items():
            if f"{word} input" in text.lower() or f"{word} inputs" in text.lower():
                required["in"] = val
                break

    if "out" not in required:
        for word, val in _WORD_NUMS.items():
            if f"{word} output" in text.lower() or f"{word} outputs" in text.lower():
                required["out"] = val
                break

    if "in" in required and "out" in required:
        port_form = f"{required['in']}x{required['out']}"
        return port_form, required

    if "in" not in required or "out" not in required:
        channel_match = _CHANNEL_RE.search(text.lower())
        common_match = _COMMON_RE.search(text.lower())
        channel_n = int(channel_match.group(1)) if channel_match else None
        common_n = int(common_match.group(1)) if common_match else None

        if channel_n is None:
            for word, val in _WORD_NUMS.items():
                if f"{word} channel" in text.lower() or f"{word} channels" in text.lower():
                    channel_n = val
                    break

        if common_n is None:
            for word, val in _WORD_NUMS.items():
                if f"{word} common" in text.lower() or f"{word} bus" in text.lower():
                    common_n = val
                    break

        if channel_n is not None and common_n is None and ("common port" in text.lower() or "bus port" in text.lower()):
            common_n = 1

        if channel_n is not None and "out" not in required:
            required["out"] = channel_n
        if common_n is not None and "in" not in required:
            required["in"] = common_n

        if "in" in required and "out" in required:
            port_form = f"{required['in']}x{required['out']}"

    return port_form, required


def _extract_port_mapping(text: str) -> List[Tuple[int, int]]:
    if not text:
        return []
    pairs: List[Tuple[int, int]] = []
    for m in _PORT_PAIR_RE.finditer(text):
        pairs.append((int(m.group(1)), int(m.group(2))))
    for m in _PORT_PAIR_IO_RE.finditer(text):
        pairs.append((int(m.group(1)), int(m.group(2))))

    if not pairs:
        return []

    nums = [n for p in pairs for n in p]
    if 0 not in nums and min(nums) == 1:
        pairs = [(a - 1, b - 1) for a, b in pairs]

    seen = set()
    unique: List[Tuple[int, int]] = []
    for a, b in pairs:
        key = (a, b)
        if key in seen:
            continue
        seen.add(key)
        unique.append((a, b))
    return unique


def _detect_splitter_tree(brief: DesignBrief) -> Optional[int]:
    texts: List[str] = []
    if brief.title:
        texts.append(brief.title)
    if brief.summary:
        texts.append(brief.summary)
    if brief.objective and brief.objective.target_behavior:
        texts.append(brief.objective.target_behavior)
    if brief.wiring_notes:
        texts.extend([n for n in brief.wiring_notes if n])
    for b in brief.blocks:
        if b.role:
            texts.append(b.role)
        if b.notes:
            texts.append(b.notes)

    combined = " ".join(texts).lower()
    if "splitter" not in combined and "mmi" not in combined:
        return None
    if "tree" not in combined and "cascade" not in combined and "cascaded" not in combined and "binary" not in combined:
        return None

    m = _PORT_FORM_RE.search(combined.replace("×", "x"))
    if not m:
        return None
    try:
        in_n = int(m.group(1))
        out_n = int(m.group(2))
    except Exception:
        return None
    if in_n != 1 or out_n < 2:
        return None
    if out_n & (out_n - 1) != 0:
        return None
    return out_n


def _detect_mesh(brief: DesignBrief) -> Optional[Tuple[int, int]]:
    texts: List[str] = []
    if brief.title:
        texts.append(brief.title)
    if brief.summary:
        texts.append(brief.summary)
    if brief.objective and brief.objective.target_behavior:
        texts.append(brief.objective.target_behavior)
    if brief.wiring_notes:
        texts.extend([n for n in brief.wiring_notes if n])
    for b in brief.blocks:
        if b.role:
            texts.append(b.role)
        if b.notes:
            texts.append(b.notes)

    combined = " ".join(texts).lower()
    if "mesh" not in combined:
        return None

    normalized = combined.replace("*", "x").replace("\u00d7", "x")

    row_col_match = re.search(
        r"\b(\d+)\s*(?:row|rows)\b.*?\b(\d+)\s*(?:col|cols|columns)\b",
        normalized,
    )
    if row_col_match:
        rows = int(row_col_match.group(1))
        cols = int(row_col_match.group(2))
    else:
        matches = list(_PORT_FORM_RE.finditer(normalized))
        if not matches:
            return None
        best = None
        for m in matches:
            try:
                r = int(m.group(1))
                c = int(m.group(2))
            except Exception:
                continue
            area = r * c
            if best is None or area > best[0]:
                best = (area, r, c)
        if best is None:
            return None
        _, rows, cols = best
    if rows < 2 or cols < 2:
        return None
    return rows, cols


def _build_mesh_plan(
    rows: int,
    cols: int,
    role_raw: str,
    role_canonical: str,
    role_variant: str,
    required_port_form: Optional[str],
    required_ports: Dict[str, int],
    connect_horizontal: bool,
) -> TopologyPlan:
    nodes: List[TopologyNode] = []
    intents: List[TopologyIntent] = []

    port_in = required_ports.get("in")
    port_out = required_ports.get("out")
    if port_in is None or port_out is None:
        if role_canonical in {"phase_shifter", "heater", "tuner"}:
            port_in, port_out = 1, 1
            required_port_form = required_port_form or "1x1"
        elif role_canonical in {"mzi_2x2", "coupler_2x2"}:
            port_in, port_out = 2, 2
            required_port_form = required_port_form or "2x2"

    port_count = 1
    if port_in is not None and port_out is not None:
        port_count = max(1, min(port_in, port_out))

    for r in range(rows):
        for c in range(cols):
            nodes.append(
                TopologyNode(
                    node_id=f"n{r}_{c}",
                    role_raw=role_raw,
                    role_canonical=role_canonical,
                    role_variant=role_variant,
                    notes="Mesh/array node; connect adjacent nodes back-to-back if specified.",
                    required_port_form=required_port_form,
                    required_ports=dict(required_ports),
                    kind="component",
                    index_in_role=r * cols + c,
                )
            )

    def node_id(r: int, c: int) -> str:
        return f"n{r}_{c}"

    if connect_horizontal:
        for r in range(rows):
            for c in range(cols):
                if c + 1 < cols:
                    for p in range(port_count):
                        intents.append(
                            TopologyIntent(
                                a=node_id(r, c),
                                a_port=f"out{p}",
                                b=node_id(r, c + 1),
                                b_port=f"in{p}",
                                intent="signal",
                            )
                        )

    return TopologyPlan(
        nodes=nodes,
        intents=intents,
        top_ports={},
        notes=[
            f"Mesh topology: {rows} rows x {cols} cols.",
            "Adjacent nodes are connected horizontally only, with port index preserved."
            if connect_horizontal
            else "Array topology: no inter-node connections.",
        ],
    )


def _build_splitter_tree_plan(brief: DesignBrief, out_n: int) -> TopologyPlan:
    splitters = out_n - 1
    nodes: List[TopologyNode] = []
    intents: List[TopologyIntent] = []
    top_ports: Dict[str, Dict[str, str]] = {}

    for i in range(splitters):
        nodes.append(
            TopologyNode(
                node_id=f"n{i}",
                role_raw="1x2 MMI splitter (tree)",
                role_canonical="splitter_1x2",
                role_variant="",
                notes="Binary splitter tree node (1 input, 2 outputs).",
                required_port_form="1x2",
                required_ports={"in": 1, "out": 2},
                kind="component",
                index_in_role=i,
            )
        )

    for i in range(splitters):
        left = 2 * i + 1
        right = 2 * i + 2
        if left < splitters:
            intents.append(
                TopologyIntent(
                    a=f"n{i}", a_port="out0",
                    b=f"n{left}", b_port="in0",
                    intent="signal",
                )
            )
        if right < splitters:
            intents.append(
                TopologyIntent(
                    a=f"n{i}", a_port="out1",
                    b=f"n{right}", b_port="in0",
                    intent="signal",
                )
            )

    leaves = [i for i in range(splitters) if (2 * i + 1) >= splitters]
    top_ports["in0"] = {"part": "n0", "port": "in0"}
    out_idx = 0
    for li in leaves:
        top_ports[f"out{out_idx}"] = {"part": f"n{li}", "port": "out0"}
        out_idx += 1
        top_ports[f"out{out_idx}"] = {"part": f"n{li}", "port": "out1"}
        out_idx += 1

    return TopologyPlan(
        nodes=nodes,
        intents=intents,
        top_ports=top_ports,
        notes=list(brief.wiring_notes or []),
    )


def _wants_output_grating_couplers(brief: DesignBrief) -> Tuple[bool, str]:
    for b in brief.blocks:
        if normalize_role(b.role).canonical == "grating_coupler":
            return True, b.role

    texts: List[str] = []
    if brief.title:
        texts.append(brief.title)
    if brief.summary:
        texts.append(brief.summary)
    if brief.objective and brief.objective.target_behavior:
        texts.append(brief.objective.target_behavior)
    if brief.wiring_notes:
        texts.extend([n for n in brief.wiring_notes if n])

    combined = " ".join(texts).lower()
    if "grating coupler" in combined or "grating_coupler" in combined or "gc" in combined:
        return True, "grating coupler"
    return False, "grating coupler"


def _attach_output_grating_couplers(
    plan: TopologyPlan,
    out_n: int,
    role_raw: str,
) -> TopologyPlan:
    nodes = list(plan.nodes)
    intents = list(plan.intents)
    top_ports = dict(plan.top_ports)

    for i in range(out_n):
        gc_id = f"gc{i}"
        nodes.append(
            TopologyNode(
                node_id=gc_id,
                role_raw=role_raw,
                role_canonical="grating_coupler",
                role_variant="",
                notes="Grating coupler attached to splitter-tree output.",
                required_port_form="1x1",
                required_ports={"in": 1, "out": 1},
                kind="component",
                index_in_role=i,
            )
        )
        tp = top_ports.get(f"out{i}")
        if tp:
            intents.append(
                TopologyIntent(
                    a=tp["part"],
                    a_port=tp["port"],
                    b=gc_id,
                    b_port="in0",
                    intent="signal",
                )
            )
            top_ports[f"out{i}"] = {"part": gc_id, "port": "out0"}

    return TopologyPlan(
        nodes=nodes,
        intents=intents,
        top_ports=top_ports,
        notes=list(plan.notes or []),
    )


def build_topology_plan(brief: DesignBrief) -> TopologyPlan:
    def _mesh_role_from_brief(rows: int, cols: int) -> Tuple[str, str, str, Optional[str], Dict[str, int]]:
        for bh in brief.blocks:
            nr = normalize_role(bh.role)
            if nr.canonical in {"interconnect", "io_port"}:
                continue
            combined_text = " ".join([
                bh.role or "",
                bh.notes or "",
                brief.summary or "",
                brief.objective.target_behavior or "",
            ])
            req_form, req_ports = _parse_port_requirements(combined_text)
            grid_form = f"{rows}x{cols}"
            if req_form == grid_form:
                req_form = None
                req_ports = {}
            if nr.canonical in {"phase_shifter", "heater", "tuner"}:
                req_form = "1x1"
                req_ports = {"in": 1, "out": 1}
            elif nr.canonical in {"mzi_2x2", "coupler_2x2"}:
                req_form = "2x2"
                req_ports = {"in": 2, "out": 2}
            return (bh.role or "mesh node", nr.canonical, nr.variant or "", req_form, req_ports)
        return ("mesh node", "mzi_2x2", "", "2x2", {"in": 2, "out": 2})

    mesh_dims = _detect_mesh(brief)
    if mesh_dims:
        rows, cols = mesh_dims
        role_raw, role_canonical, role_variant, req_form, req_ports = _mesh_role_from_brief(rows, cols)
        return _build_mesh_plan(
            rows,
            cols,
            role_raw,
            role_canonical,
            role_variant,
            req_form,
            req_ports,
            connect_horizontal=True,
        )

    out_n = _detect_splitter_tree(brief)
    if out_n:
        plan = _build_splitter_tree_plan(brief, out_n)
        wants_gc, role_raw = _wants_output_grating_couplers(brief)
        if wants_gc:
            return _attach_output_grating_couplers(plan, out_n, role_raw)
        return plan

    nodes: List[TopologyNode] = []
    intents: List[TopologyIntent] = []

    for block_index, bh in enumerate(brief.blocks):
        nr = normalize_role(bh.role)

        if nr.canonical in {"interconnect", "io_port"}:
            continue

        combined_text = " ".join(
            [
                bh.role or "",
                bh.notes or "",
                brief.summary or "",
                brief.objective.target_behavior or "",
            ]
        )
        req_form, req_ports = _parse_port_requirements(combined_text)
        if nr.canonical in {"edge_coupler", "grating_coupler"}:
            req_form = "1x1"
            req_ports = {"in": 1, "out": 1}
        elif nr.canonical in {"phase_shifter", "heater", "tuner"}:
            if not req_ports:
                req_form = "1x1"
                req_ports = {"in": 1, "out": 1}

        n = max(1, int(bh.count or 1))
        for k in range(n):
            suffix = f"_{k}" if n > 1 else ""
            node_id = f"n{block_index}{suffix}"
            nodes.append(
                TopologyNode(
                    node_id=node_id,
                    role_raw=bh.role,
                    role_canonical=nr.canonical,
                    role_variant=(nr.variant or ""),
                    notes=bh.notes,
                    required_port_form=req_form,
                    required_ports=req_ports,
                    kind="component",
                    index_in_role=k,
                )
            )

    array_text = " ".join(
        [
            brief.title or "",
            brief.summary or "",
            brief.objective.target_behavior or "",
            " ".join(brief.wiring_notes or []),
        ]
    ).lower()
    is_parallel_array = "array" in array_text and ("y direction" in array_text or "along the y" in array_text or "along y" in array_text)
    pairwise_text = (
        "each" in array_text
        and (
            "connected to" in array_text
            or "connect to" in array_text
            or "connected with" in array_text
        )
    )

    io_n = int(brief.objective.io_ports or 1)
    if nodes:
        in_req = [n.required_ports.get("in") for n in nodes if n.required_ports.get("in") is not None]
        out_req = [n.required_ports.get("out") for n in nodes if n.required_ports.get("out") is not None]
        if in_req or out_req:
            in_min = min(in_req) if in_req else None
            out_min = min(out_req) if out_req else None
            if in_min is not None and out_min is not None:
                io_n = min(io_n, in_min, out_min)
            elif in_min is not None:
                io_n = min(io_n, in_min)
            elif out_min is not None:
                io_n = min(io_n, out_min)

        if is_parallel_array:
            groups: Dict[str, List[TopologyNode]] = {}
            for n in nodes:
                groups.setdefault(n.role_canonical, []).append(n)

            if len(groups) == 2:
                keys = list(groups.keys())
                a_key = keys[0]
                b_key = keys[1]
                if "grating_coupler" in keys:
                    b_key = "grating_coupler"
                    a_key = keys[0] if keys[1] == "grating_coupler" else keys[1]
                if "edge_coupler" in keys:
                    a_key = "edge_coupler"
                    b_key = keys[0] if keys[1] == "edge_coupler" else keys[1]

                a_nodes = sorted(groups[a_key], key=lambda n: n.index_in_role)
                b_nodes = sorted(groups[b_key], key=lambda n: n.index_in_role)
                if len(a_nodes) == len(b_nodes) and len(a_nodes) > 1:
                    if pairwise_text or "grating_coupler" in keys:
                        for i in range(len(a_nodes)):
                            intents.append(
                                TopologyIntent(
                                    a=a_nodes[i].node_id,
                                    a_port="out0",
                                    b=b_nodes[i].node_id,
                                    b_port="in0",
                                    intent="signal",
                                )
                            )
                        return TopologyPlan(
                            nodes=nodes,
                            intents=intents,
                            top_ports={},
                            notes=list(brief.wiring_notes or []),
                        )

            return TopologyPlan(
                nodes=nodes,
                intents=[],
                top_ports={},
                notes=list(brief.wiring_notes or []),
            )

        # fan-out special case: splitter feeds multiple downstream blocks
        splitter = nodes[0]
        out_n = splitter.required_ports.get("out") if splitter.required_ports else None
        if splitter.role_canonical == "splitter_1x2" and out_n and len(nodes) >= 1 + out_n:
            top_ports: Dict[str, Dict[str, str]] = {"in0": {"part": splitter.node_id, "port": "in0"}}
            for idx in range(out_n):
                target = nodes[1 + idx]
                intents.append(
                    TopologyIntent(
                        a=splitter.node_id,
                        a_port=f"out{idx}",
                        b=target.node_id,
                        b_port="in0",
                        intent="signal",
                    )
                )
                top_ports[f"out{idx}"] = {"part": target.node_id, "port": "out0"}
        else:
            a0 = nodes[0].node_id
            z0 = nodes[-1].node_id

            top_ports = {}
            for p in range(io_n):
                top_ports[f"in{p}"] = {"part": a0, "port": f"in{p}"}
                top_ports[f"out{p}"] = {"part": z0, "port": f"out{p}"}

            mapping_text = " ".join(
                [
                    brief.title or "",
                    brief.summary or "",
                    brief.objective.target_behavior or "",
                    " ".join(brief.wiring_notes or []),
                ]
            ).lower()
            port_mapping = _extract_port_mapping(mapping_text)

            for i in range(len(nodes) - 1):
                a = nodes[i].node_id
                b = nodes[i + 1].node_id
                if port_mapping:
                    for src_idx, dst_idx in port_mapping:
                        intents.append(
                            TopologyIntent(
                                a=a, a_port=f"out{src_idx}",
                                b=b, b_port=f"in{dst_idx}",
                                intent="signal",
                            )
                        )
                else:
                    for p in range(io_n):
                        intents.append(
                            TopologyIntent(
                                a=a, a_port=f"out{p}",
                                b=b, b_port=f"in{p}",
                                intent="signal",
                            )
                        )
    else:
        top_ports = {}

    return TopologyPlan(
        nodes=nodes,
        intents=intents,
        top_ports=top_ports,
        notes=list(brief.wiring_notes or []),
    )


def topology_to_dot(plan: TopologyPlan) -> str:
    lines = ["digraph AutoGDS_Topology {", "  rankdir=LR;"]
    for n in plan.nodes:
        label = f"{n.node_id}\\n{n.role_canonical}"
        lines.append(f'  "{n.node_id}" [shape=box,label="{label}"];')
    for e in plan.intents:
        lines.append(f'  "{e.a}" -> "{e.b}" [label="{e.a_port}->{e.b_port}"];')
    lines.append("}")
    return "\n".join(lines) + "\n"
