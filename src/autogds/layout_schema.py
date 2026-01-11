from __future__ import annotations

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class NetlistInstance(BaseModel):
    name: str
    symbol: str
    params: Dict[str, float | int | str] = Field(default_factory=dict)


class NetlistLink(BaseModel):
    a: str
    a_port: str
    b: str
    b_port: str


class LayoutNetlist(BaseModel):
    schema_rev: Literal["r1"] = "r1"
    instances: List[NetlistInstance] = Field(default_factory=list)
    links: List[NetlistLink] = Field(default_factory=list)
    top_ports: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    layout_hint: Optional[str] = None
    issues: List[str] = Field(default_factory=list)


class Footprint(BaseModel):
    name: str
    symbol: str
    width_um: float
    height_um: float
    ports: List[str] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)


class LayoutFootprints(BaseModel):
    schema_rev: Literal["r1"] = "r1"
    footprints: List[Footprint] = Field(default_factory=list)


class Placement(BaseModel):
    name: str
    symbol: str
    x_um: float
    y_um: float
    rotation_deg: float = 0.0
    width_um: float = 0.0
    height_um: float = 0.0
    issues: List[str] = Field(default_factory=list)


class LayoutPlacements(BaseModel):
    schema_rev: Literal["r1"] = "r1"
    placements: List[Placement] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)


class Route(BaseModel):
    link_id: str
    a: str
    a_port: str
    b: str
    b_port: str
    points: List[Dict[str, float]] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)


class LayoutRoutes(BaseModel):
    schema_rev: Literal["r1"] = "r1"
    routes: List[Route] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)


class PlacementOverlap(BaseModel):
    a: str
    b: str
    dx_um: float
    dy_um: float


class LayoutPrecheck(BaseModel):
    schema_rev: Literal["r1"] = "r1"
    overlaps: List[PlacementOverlap] = Field(default_factory=list)
    route_issues: List[str] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)


class LayoutEmit(BaseModel):
    schema_rev: Literal["r1"] = "r1"
    gds_path: str = ""
    issues: List[str] = Field(default_factory=list)


class LayoutReport(BaseModel):
    schema_rev: Literal["r1"] = "r1"
    ok: bool = True
    issues: List[str] = Field(default_factory=list)
