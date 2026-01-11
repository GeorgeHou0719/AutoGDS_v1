from __future__ import annotations

import re
from typing import Dict, List, Tuple
from autogds.schema import Blueprint, Part, Link, TopologyPlan, Option, DesignBrief


_PARAM_KV_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*(?:=|:)\s*([0-9]+(?:\.[0-9]+)?)\b")
_PARAM_KV_UNIT_RE = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_ ]*)\s*(?:=|:)\s*([0-9]+(?:\.[0-9]+)?)\s*(nm|um|µm)\b",
    re.IGNORECASE,
)
_PARAM_UNIT_RE = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_ ]*)\s+([0-9]+(?:\.[0-9]+)?)\s*(nm|um|µm)\b",
    re.IGNORECASE,
)


_PARAM_UNIT_REV_RE = re.compile(
    r"\b([0-9]+(?:\.[0-9]+)?)\s*(nm|um)\s+([A-Za-z_][A-Za-z0-9_ ]*)\b",
    re.IGNORECASE,
)


def _normalize_param_key(raw_key: str) -> str | None:
    if not raw_key:
        return None
    key = raw_key.strip().lower().replace(' ', '_')
    if 'gap' in key:
        return 'gap'
    if 'coupling' in key and 'length' in key:
        return 'length'
    if 'path_difference' in key or 'path_diff' in key or 'delta_length' in key or key == 'delta':
        return 'delta_length'
    if 'path' in key and 'difference' in key:
        return 'delta_length'
    if 'differential' in key and 'path' in key:
        return 'delta_length'
    if 'radius' in key:
        return 'radius'
    if key.endswith('_length'):
        return 'length'
    if key.endswith('_width'):
        return 'width'
    if key in {'length', 'width'}:
        return key
    if len(key.split('_')) > 4:
        return None
    return key


def _extract_param_candidates(text: str) -> Dict[str, float]:
    if not text:
        return {}
    text_norm = (
        text.replace("ΔL", "delta_length")
        .replace("Δl", "delta_length")
        .replace("Δ", "delta")
        .replace("×", "x")
        .replace("µm", "um")
        .replace("μm", "um")
        .replace("‑", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("-", " ")
        .replace("(", " ")
        .replace(")", " ")
    ).lower()
    found: Dict[str, float] = {}
    for m in _PARAM_KV_RE.finditer(text_norm):
        key = m.group(1)
        try:
            val = float(m.group(2))
        except Exception:
            continue
        if key and key not in found:
            found[key] = val

    for m in _PARAM_KV_UNIT_RE.finditer(text_norm):
        raw_key = m.group(1)
        try:
            val = float(m.group(2))
        except Exception:
            continue
        unit = m.group(3).lower()
        if unit == "nm":
            val = val / 1000.0
        key = _normalize_param_key(raw_key)
        if key and key not in found:
            found[key] = val

    for m in _PARAM_UNIT_RE.finditer(text_norm):
        raw_key = m.group(1)
        try:
            val = float(m.group(2))
        except Exception:
            continue
        unit = m.group(3).lower()
        if unit == "nm":
            val = val / 1000.0
        key = _normalize_param_key(raw_key)
        if key and key not in found:
            found[key] = val
        if key is None and ("path length" in raw_key or "differential path" in raw_key):
            found["delta_length"] = val
    for m in _PARAM_UNIT_REV_RE.finditer(text_norm):
        raw_key = m.group(3)
        try:
            val = float(m.group(1))
        except Exception:
            continue
        unit = m.group(2).lower()
        if unit == "nm":
            val = val / 1000.0
        key = _normalize_param_key(raw_key)
        if key and key not in found:
            found[key] = val
    return found


def _build_logical_port_map(required_ports: Dict[str, int], ports_exposed: List[str]) -> Tuple[Dict[str, str], List[str]]:
    if not required_ports or not ports_exposed:
        return {}, (["no_ports_exposed"] if required_ports and not ports_exposed else [])

    logical_map: Dict[str, str] = {}
    issues: List[str] = []
    idx = 0

    in_n = required_ports.get("in")
    out_n = required_ports.get("out")

    if in_n is not None:
        for i in range(in_n):
            if idx < len(ports_exposed):
                logical_map[f"in{i}"] = ports_exposed[idx]
                idx += 1
            else:
                issues.append(f"missing_exposed_port_for_in{i}")

    if out_n is not None:
        for i in range(out_n):
            if idx < len(ports_exposed):
                logical_map[f"out{i}"] = ports_exposed[idx]
                idx += 1
            else:
                issues.append(f"missing_exposed_port_for_out{i}")

    return logical_map, issues


def bind_plan_to_blueprint(
    plan: TopologyPlan,
    chosen: Dict[str, Option],
    brief: DesignBrief,
    entry_map: Dict[Tuple[str, str], object],
) -> Blueprint:
    parts: List[Part] = []
    parts_by_name: Dict[str, Part] = {}
    for node in plan.nodes:
        opt = chosen.get(node.node_id)
        if opt is None:
            part = Part(name=node.node_id, symbol="(unbound)", params={"role": node.role_canonical})
            parts.append(part)
            parts_by_name[part.name] = part
        else:
            entry = entry_map.get((opt.symbol, opt.source_file))
            contract = getattr(entry, "contract", None) if entry else None

            params = {"role": node.role_canonical}
            param_issues: List[str] = []
            port_map_issues: List[str] = []
            logical_port_map: Dict[str, str] = {}

            candidate_params = _extract_param_candidates(node.notes or "")
            args_sig = getattr(contract, "args_sig", {}) if contract else {}
            if candidate_params:
                for k, v in candidate_params.items():
                    if args_sig and k in args_sig:
                        params[k] = v
                    else:
                        param_issues.append(f"param_not_in_args_sig:{k}")

            if contract and getattr(contract, "ports_exposed", None):
                logical_port_map, port_map_issues = _build_logical_port_map(
                    required_ports=getattr(node, "required_ports", {}) or {},
                    ports_exposed=list(contract.ports_exposed or []),
                )

            parts.append(
                Part(
                    name=node.node_id,
                    symbol=opt.symbol,
                    params=params,
                    logical_port_map=logical_port_map,
                    param_issues=param_issues,
                    port_map_issues=port_map_issues,
                )
            )
            parts_by_name[node.node_id] = parts[-1]

    links: List[Link] = []
    for it in plan.intents:
        a_part = parts_by_name.get(it.a)
        b_part = parts_by_name.get(it.b)

        a_port = it.a_port
        b_port = it.b_port

        if a_part and a_part.logical_port_map:
            mapped = a_part.logical_port_map.get(it.a_port)
            if mapped:
                a_port = mapped
            else:
                a_part.port_map_issues.append(f"missing_logical_port:{it.a_port}")

        if b_part and b_part.logical_port_map:
            mapped = b_part.logical_port_map.get(it.b_port)
            if mapped:
                b_port = mapped
            else:
                b_part.port_map_issues.append(f"missing_logical_port:{it.b_port}")

        links.append(Link(a=it.a, a_port=a_port, b=it.b, b_port=b_port))

    return Blueprint(parts=parts, links=links, top_ports=dict(plan.top_ports))
