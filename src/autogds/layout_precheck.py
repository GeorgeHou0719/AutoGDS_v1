from __future__ import annotations

from typing import List

from autogds.layout_schema import LayoutPlacements, LayoutRoutes, LayoutPrecheck, PlacementOverlap


def _overlap_1d(a0: float, a1: float, b0: float, b1: float) -> float:
    left = max(a0, b0)
    right = min(a1, b1)
    return max(0.0, right - left)


def precheck_layout(
    placements: LayoutPlacements,
    routes: LayoutRoutes,
) -> LayoutPrecheck:
    overlaps: List[PlacementOverlap] = []
    route_issues: List[str] = []
    issues: List[str] = []

    pls = placements.placements
    for i in range(len(pls)):
        a = pls[i]
        a_x0 = a.x_um
        a_x1 = a.x_um + a.width_um
        a_y0 = a.y_um
        a_y1 = a.y_um + a.height_um
        for j in range(i + 1, len(pls)):
            b = pls[j]
            b_x0 = b.x_um
            b_x1 = b.x_um + b.width_um
            b_y0 = b.y_um
            b_y1 = b.y_um + b.height_um
            dx = _overlap_1d(a_x0, a_x1, b_x0, b_x1)
            dy = _overlap_1d(a_y0, a_y1, b_y0, b_y1)
            if dx > 0 and dy > 0:
                overlaps.append(
                    PlacementOverlap(
                        a=a.name,
                        b=b.name,
                        dx_um=dx,
                        dy_um=dy,
                    )
                )

    for r in routes.routes:
        if not r.points:
            route_issues.append(f"empty_route:{r.link_id}")

    if overlaps:
        issues.append("overlaps_detected")
    if route_issues:
        issues.append("route_issues_detected")

    return LayoutPrecheck(overlaps=overlaps, route_issues=route_issues, issues=issues)
