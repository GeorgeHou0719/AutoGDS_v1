from __future__ import annotations

from typing import Set, Dict
from autogds.schema import Blueprint, BlueprintReport, BlueprintIssue


def verify_blueprint(bp: Blueprint) -> BlueprintReport:
    issues = []
    ok = True

    part_names = [p.name for p in bp.parts]
    name_set: Set[str] = set()
    part_by_name: Dict[str, object] = {}
    for n in part_names:
        if n in name_set:
            ok = False
            issues.append(BlueprintIssue(severity="error", code="DUP_PART", message="Duplicate part name", data={"part": n}))
        name_set.add(n)
    for p in bp.parts:
        part_by_name[p.name] = p

    # link endpoint existence
    for i, lk in enumerate(bp.links):
        if lk.a not in name_set:
            ok = False
            issues.append(BlueprintIssue(severity="error", code="BAD_LINK_A", message="Link endpoint a missing", data={"i": i, "a": lk.a}))
        if lk.b not in name_set:
            ok = False
            issues.append(BlueprintIssue(severity="error", code="BAD_LINK_B", message="Link endpoint b missing", data={"i": i, "b": lk.b}))

        a_part = part_by_name.get(lk.a)
        b_part = part_by_name.get(lk.b)
        if a_part and a_part.logical_port_map:
            if lk.a_port not in a_part.logical_port_map.values():
                issues.append(
                    BlueprintIssue(
                        severity="warn",
                        code="LINK_PORT_UNKNOWN_A",
                        message="Link uses port not in logical_port_map (a)",
                        data={"i": i, "a": lk.a, "port": lk.a_port},
                    )
                )
        if b_part and b_part.logical_port_map:
            if lk.b_port not in b_part.logical_port_map.values():
                issues.append(
                    BlueprintIssue(
                        severity="warn",
                        code="LINK_PORT_UNKNOWN_B",
                        message="Link uses port not in logical_port_map (b)",
                        data={"i": i, "b": lk.b, "port": lk.b_port},
                    )
                )

    # top ports existence
    for tp, ref in bp.top_ports.items():
        part = ref.get("part", "")
        port = ref.get("port", "")
        if part and part not in name_set:
            ok = False
            issues.append(BlueprintIssue(severity="error", code="BAD_TOPPORT", message="Top port points to missing part", data={"top_port": tp, "part": part, "port": port}))
        if part and part in part_by_name:
            p = part_by_name[part]
            if p.logical_port_map:
                if port and port not in p.logical_port_map:
                    issues.append(
                        BlueprintIssue(
                            severity="warn",
                            code="TOPPORT_UNKNOWN_LOGICAL",
                            message="Top port refers to unknown logical port",
                            data={"top_port": tp, "part": part, "port": port},
                        )
                    )

    # propagate per-part port mapping issues
    for p in bp.parts:
        for msg in p.port_map_issues or []:
            severity = "warn"
            if msg.startswith("missing_logical_port") or msg.startswith("missing_exposed_port") or msg == "no_ports_exposed":
                severity = "error"
                ok = False
            issues.append(
                BlueprintIssue(
                    severity=severity,
                    code="PORT_MAP_ISSUE",
                    message=msg,
                    data={"part": p.name},
                )
            )

    # propagate per-part parameter issues
    for p in bp.parts:
        for msg in p.param_issues or []:
            issues.append(
                BlueprintIssue(
                    severity="warn",
                    code="PARAM_ISSUE",
                    message=msg,
                    data={"part": p.name},
                )
            )

    # connectivity hint (non-fatal)
    if bp.parts and not bp.links and len(bp.parts) > 1:
        issues.append(BlueprintIssue(severity="warn", code="NO_LINKS", message="Blueprint has multiple parts but no links", data={"parts": len(bp.parts)}))

    return BlueprintReport(ok=ok, issues=issues)
