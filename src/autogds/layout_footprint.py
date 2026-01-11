from __future__ import annotations

import re
from typing import Dict, List, Optional

from autogds.layout_schema import Footprint, LayoutFootprints


_FP_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*um?\s*[xX×]\s*([0-9]+(?:\.[0-9]+)?)")


def _parse_footprint(spec: Dict[str, object]) -> Optional[tuple[float, float]]:
    if not spec:
        return None
    for k, v in spec.items():
        if "footprint" not in str(k).lower():
            continue
        text = str(v)
        m = _FP_RE.search(text)
        if m:
            return float(m.group(1)), float(m.group(2))
    return None


def extract_footprints(parts: List[object], catalog_entries: List[object]) -> LayoutFootprints:
    sym_to_entry = {c.symbol: c for c in catalog_entries}

    footprints: List[Footprint] = []
    for part in parts:
        issues: List[str] = []
        contract = None
        entry = sym_to_entry.get(part.symbol)
        if entry:
            contract = getattr(entry, "contract", None)

        size = None
        ports: List[str] = []
        if contract:
            size = _parse_footprint(getattr(contract, "spec", {}) or {})
            ports = list(getattr(contract, "ports_exposed", []) or [])

        if size is None:
            size = (50.0, 20.0)
            issues.append("placeholder_size")

        if not ports:
            issues.append("no_ports_exposed")

        footprints.append(
            Footprint(
                name=part.name,
                symbol=part.symbol,
                width_um=size[0],
                height_um=size[1],
                ports=ports,
                issues=issues,
            )
        )

    return LayoutFootprints(footprints=footprints)
