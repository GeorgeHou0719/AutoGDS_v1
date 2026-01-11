from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class NormalizedRole:
    canonical: str
    hints: List[str]
    variant: Optional[str] = None  # e.g. "splitter", "combiner", "thermal", "eo"

    def to_query(self) -> str:
        # canonical first, then hints; remove duplicates while preserving order
        seen = set()
        parts = []
        for w in [self.canonical, *self.hints]:
            w = w.strip()
            if not w or w in seen:
                continue
            seen.add(w)
            parts.append(w)
        return " ".join(parts)


def _clean(text: str) -> str:
    t = text.lower()
    # normalize common unicode dashes/quotes already fixed by your utf-8 work, but keep robust
    t = t.replace("–", "-").replace("—", "-")
    # remove parentheses content markers but keep words
    t = re.sub(r"[(){}\[\]]", " ", t)
    t = re.sub(r"[/,:;]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def normalize_role(role_text: str) -> NormalizedRole:
    """
    Map free-form role text to canonical tags + hints used for retrieval.
    Keep it conservative: only a few high-confidence rules.
    """
    t = _clean(role_text)

    # helpers
    def has(*kw: str) -> bool:
        return all(k in t for k in kw)

    def any_has(*kw: str) -> bool:
        return any(k in t for k in kw)
    # 1) MZI
    if any_has("mzi", "mach zehnder", "mach-zhender", "interferometer"):
        hints = ["mzi", "mach_zehnder", "2x2", "interferometer"]
        return NormalizedRole(canonical="mzi_2x2", hints=hints)

    # 2) 2x2 coupler (MMI / directional / 3dB)
    if "coupler" in t or any_has("3 db") or any_has("3db") or "50:50" in t:
        variant = None
        if any_has("splitter") or any_has("split"):
            variant = "splitter"
        if any_has("combiner") or any_has("combine"):
            variant = "combiner"
        if any_has("2x2") or any_has("2 x 2") or any_has("3db") or any_has("3 db") or "50:50" in t:
            hints = ["coupler", "2x2", "3db", "50:50", "mmi", "directional"]
            return NormalizedRole(canonical="coupler_2x2", hints=hints, variant=variant)

    # 3) phase shifter (thermal / EO)
    if any_has("phase") or any_has("shifter") or any_has("heater") or any_has("thermo") or any_has("electro"):
        variant = None
        if any_has("thermal") or any_has("thermo") or any_has("heater"):
            variant = "thermal"
        if any_has("eo") or any_has("electro") or any_has("pn") or any_has("pin"):
            variant = "eo"
        hints = ["phase_shifter", "heater", "thermal", "eo", "tuning", "pi"]
        return NormalizedRole(canonical="phase_shifter", hints=hints, variant=variant)

    # 4) ring resonator / MRR
    if any_has("ring") or any_has("mrr") or any_has("micro ring") or any_has("micro-ring"):
        hints = ["ring", "mrr", "resonator", "coupler", "radius"]
        return NormalizedRole(canonical="ring_resonator", hints=hints)

    # 5) couplers to fiber (edge / grating)
    if any_has("edge") and any_has("coupler"):
        hints = ["edge_coupler", "facet", "taper"]
        return NormalizedRole(canonical="edge_coupler", hints=hints)

    if any_has("grating") or (any_has("gc") and any_has("coupler")):
        hints = ["grating_coupler", "grating coupler", "gc", "fiber", "period"]
        return NormalizedRole(canonical="grating_coupler", hints=hints)

    # 6) crossing
    if any_has("crossing"):
        hints = ["crossing", "x", "low_crosstalk"]
        return NormalizedRole(canonical="crossing", hints=hints)

    # 7) splitter/combiner 1x2 / y-branch
    if any_has("y") and any_has("branch") or any_has("y-branch") or any_has("splitter 1x2") or any_has("1x2") or any_has("power splitter") or any_has("splitter"):
        hints = ["y_branch", "splitter", "power splitter", "1x2", "directional coupler", "coupler", "mmi", "passive"]
        return NormalizedRole(canonical="splitter_1x2", hints=hints)

    # 8) modulator / photodiode (keep broad)
    if any_has("modulator") or any_has("mzm"):
        hints = ["modulator", "mzm", "pn", "eo"]
        return NormalizedRole(canonical="modulator", hints=hints)

    if any_has("photodiode") or any_has("pin diode") or any_has("pindiode"):
        hints = ["photodiode", "pd", "pin", "detector"]
        return NormalizedRole(canonical="photodiode", hints=hints)

    # 0) interconnect / routing (not a library cell)
    if any_has("interconnect") or any_has("routing") or any_has("route") or any_has("waveguide") or any_has("arm") or any_has("arms"):
        hints = ["waveguide", "route", "routing", "arm", "interconnect"]
        return NormalizedRole(canonical="interconnect", hints=hints)

    # 0b) IO ports (not a library cell)
    if re.search(r"\bio\b", t) or re.search(r"\bi/o\b", t) or any_has("input") or any_has("output") or any_has("ports") or any_has("port"):
        hints = ["port", "io", "input", "output"]
        return NormalizedRole(canonical="io_port", hints=hints)

    # fallback: keep original but cleaned; still add a generic hint to reduce junk
    # (we do NOT want to over-map unknown roles)
    hints = [w for w in re.split(r"\s+", t) if w]
    return NormalizedRole(canonical="generic_block", hints=hints[:8])
