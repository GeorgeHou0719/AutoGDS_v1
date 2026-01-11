# Prompt Patterns

Use these patterns to get predictable results from the brief/topology/selection pipeline.

## Core Rules
- Say the device type and port form explicitly: `2x2 MZI`, `1x4 WDM`, `1x2 splitter`.
- Provide counts and arrangement when there are multiples: `four`, `eight`, `array`, `mesh`, `tree`.
- Use concrete connection verbs: `connect`, `cascade`, `feed`, `back-to-back`.
- Add distinguishing keywords (heater type, PN/PIN, grating/edge coupler) to help selection.

## Port Forms and Topology
- Use `NxM` for port counts.
  - Example: `2x2 MZI`, `1x4 WDM`.
- For splitter cascades, include `1xN` plus `tree`.
  - Example: `1x8 splitter tree using 1x2 MMIs`.
- For meshes, describe the grid size and link style.
  - Example: `3x3 mesh of 2x2 MZIs with back-to-back links`.

## Connection Intent
- State who connects to whom.
  - `Splitter outputs feed two MZIs.`
  - `Cascade two MZIs.`
- Add port mapping only when necessary.
  - `Port 0 to port 0, port 1 to port 1.`
  - `Output port 1 to input port 1.`

## Parameters and Units
- Always include units: `10 um`, `500 nm`.
- Use common parameter names when possible:
  - `delta_length 100 um`
  - `length 320 um`
  - `width 500 nm`
- If you care about heater type, say it: `TiN heater`, `doped Si heater`, `PN`, `PIN`.

## Layout Hints
- Arrays: `arranged in an array along the y direction`.
- Parallel sets: `arranged in parallel`.
- Trees: `1x16 splitter tree` or `binary tree`.

## Examples
- `A 2x2 MZI with TiN heaters. Heater length 10 um.`
- `A power splitter connected to two 1x1 MZIs with delta_length 100 um.`
- `Layout 1x2 MMIs connected to each other for a 1x8 splitter tree.`
- `Four microrings with heaters, arranged in an array along the y direction, each connected to a grating coupler.`
