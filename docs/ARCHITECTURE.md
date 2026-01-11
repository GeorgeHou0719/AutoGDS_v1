# AutoGDS Architecture

This document describes the core pipeline and how data moves through the system.

## Pipeline Overview
1) Brief: parse a natural-language prompt into a structured design brief.
2) Topology: build a component graph (nodes + links) from the brief.
3) Selection: retrieve candidate components from the catalog and pick one per node.
4) Blueprint: bind selected components to topology with logical port mappings.
5) Netlist: normalize the blueprint into a simple netlist for layout steps.
6) Layout: footprints, placement, alignment, routing, precheck, emit GDS.

## Key Artifacts
- `brief.json`: structured description derived from the prompt.
- `topology_plan.json`: abstract component graph.
- `selection.json`: selected catalog entries per topology node.
- `blueprint.json`: bound components with logical port mappings.
- `layout_*.json`: layout stages (netlist, placements, routes, checks).
- `layout.gds`: final layout (if gdsfactory is available).

## Core Modules
- `src/autogds/flow.py`: orchestrates the pipeline end-to-end.
- `src/autogds/topology.py`: builds topology and special cases (fan-out, splitter trees).
- `src/autogds/catalog_scan.py`: scans Python catalogs and extracts contracts.
- `src/autogds/catalog_rank.py`: ranks components for selection.
- `src/autogds/blueprint_bind.py`: binds parameters and logical ports.
- `src/autogds/layout_*`: placement, routing, checks, and GDS emission.

## Catalog Contract
Each component can define a docstring-based contract:
- `ports`: port form such as `1x2`, `2x2`, `1x4`.
- `NodeLabels`: tags like `passive`, `modulator`, `WDM`.
- `Args`: default parameters and supported args.

Contracts drive:
- selection ranking,
- port mapping,
- layout footprint estimation,
- parameter passthrough.

