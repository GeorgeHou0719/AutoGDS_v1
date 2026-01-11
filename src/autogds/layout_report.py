from __future__ import annotations

from typing import List

from autogds.layout_schema import (
    LayoutReport,
    LayoutNetlist,
    LayoutFootprints,
    LayoutPlacements,
    LayoutRoutes,
    LayoutPrecheck,
    LayoutEmit,
)


def build_layout_report(
    netlist: LayoutNetlist,
    footprints: LayoutFootprints,
    placements: LayoutPlacements,
    alignments: LayoutPlacements,
    routes: LayoutRoutes,
    precheck: LayoutPrecheck,
    emit: LayoutEmit,
) -> LayoutReport:
    issues: List[str] = []

    issues.extend(netlist.issues or [])
    issues.extend([f"footprint:{i}" for i in _issues_from_footprints(footprints)])
    issues.extend([f"placement:{i}" for i in (placements.issues or [])])
    issues.extend([f"alignment:{i}" for i in (alignments.issues or [])])
    issues.extend([f"route:{i}" for i in (routes.issues or [])])
    issues.extend([f"precheck:{i}" for i in (precheck.issues or [])])
    issues.extend([f"emit:{i}" for i in (emit.issues or [])])

    ok = len(issues) == 0
    return LayoutReport(ok=ok, issues=issues)


def _issues_from_footprints(footprints: LayoutFootprints) -> List[str]:
    out: List[str] = []
    for fp in footprints.footprints:
        for msg in fp.issues or []:
            out.append(f"{fp.name}:{msg}")
    return out
