from __future__ import annotations

from typing import Dict, List

from autogds.layout_schema import LayoutPlacements, Placement, LayoutFootprints, LayoutNetlist


def align_instances(
    placements: LayoutPlacements,
    netlist: LayoutNetlist,
    footprints: LayoutFootprints,
) -> LayoutPlacements:
    fp_map: Dict[str, object] = {fp.name: fp for fp in footprints.footprints}
    issues: List[str] = list(placements.issues)

    aligned: List[Placement] = []
    for pl in placements.placements:
        fp = fp_map.get(pl.name)
        # No port orientation data available yet; keep rotation as-is.
        if not fp or not fp.ports:
            issues.append(f"alignment_skipped_no_ports:{pl.name}")
        else:
            issues.append(f"alignment_skipped_no_orientation:{pl.name}")

        aligned.append(
            Placement(
                name=pl.name,
                symbol=pl.symbol,
                x_um=pl.x_um,
                y_um=pl.y_um,
                rotation_deg=pl.rotation_deg,
                width_um=pl.width_um,
                height_um=pl.height_um,
                issues=list(pl.issues),
            )
        )

    return LayoutPlacements(placements=aligned, issues=issues)
