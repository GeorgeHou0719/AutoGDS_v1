from __future__ import annotations

from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field


class BlockHint(BaseModel):
    role: str = Field(..., description="Functional role, e.g., coupler, phase shifter, splitter")
    count: int = 1
    notes: Optional[str] = None


class Objective(BaseModel):
    wl_um_min: Optional[float] = None
    wl_um_max: Optional[float] = None
    io_ports: Optional[int] = None
    target_behavior: Optional[str] = None


class DesignBrief(BaseModel):
    schema_rev: Literal["r1"] = "r1"
    title: str
    summary: str
    blocks: List[BlockHint]
    wiring_notes: List[str] = []
    objective: Objective = Field(default_factory=Objective)

class ComponentContract(BaseModel):
    port_form: Optional[str] = None
    node_labels: List[str] = Field(default_factory=list)
    spec: Dict[str, float | int | str] = Field(default_factory=dict)
    args_doc: List[str] = Field(default_factory=list)
    args_sig: Dict[str, float | int | str | None] = Field(default_factory=dict)
    ports_exposed: List[str] = Field(default_factory=list)
    param_passthrough: Dict[str, bool] = Field(default_factory=dict)

class CatalogEntry(BaseModel):
    symbol: str
    source_file: str
    doc: str
    contract: Optional[ComponentContract] = None

class Option(BaseModel):
    symbol: str
    source_file: str
    score: float
    rationale: str
    extras: Dict[str, object] = Field(default_factory=dict)


class Part(BaseModel):
    name: str
    symbol: str
    params: Dict[str, float | int | str] = Field(default_factory=dict)
    logical_port_map: Dict[str, str] = Field(default_factory=dict)
    param_issues: List[str] = Field(default_factory=list)
    port_map_issues: List[str] = Field(default_factory=list)


class Link(BaseModel):
    a: str
    a_port: str
    b: str
    b_port: str


class Blueprint(BaseModel):
    schema_rev: Literal["r1"] = "r1"
    parts: List[Part]
    links: List[Link]
    top_ports: Dict[str, Dict[str, str]] = Field(default_factory=dict)


# -------- Topo-first additions (AutoGDS naming) --------

class TopologyNode(BaseModel):
    node_id: str
    role_raw: str
    role_canonical: str
    role_variant: str = ""
    notes: Optional[str] = None
    required_port_form: Optional[str] = None
    required_ports: Dict[str, int] = Field(default_factory=dict)
    kind: Literal["component", "virtual"] = "component"
    index_in_role: int = 0


class TopologyIntent(BaseModel):
    a: str
    a_port: str
    b: str
    b_port: str
    intent: Literal["signal", "control", "power", "thermal", "generic"] = "signal"


class TopologyPlan(BaseModel):
    schema_rev: Literal["r1"] = "r1"
    nodes: List[TopologyNode] = Field(default_factory=list)
    intents: List[TopologyIntent] = Field(default_factory=list)
    top_ports: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class BlueprintIssue(BaseModel):
    severity: Literal["info", "warn", "error"] = "warn"
    code: str
    message: str
    data: Dict[str, float | int | str] = Field(default_factory=dict)


class BlueprintReport(BaseModel):
    schema_rev: Literal["r1"] = "r1"
    ok: bool = True
    issues: List[BlueprintIssue] = Field(default_factory=list)
