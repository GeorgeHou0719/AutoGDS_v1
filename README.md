# AutoGDS: Agent-based Automatic PIC GDS Designer

## Background and Motivation
**Silicon photonic integrated circuits `(PICs)`** have become a mature industrial platform, with growing demand driven by data centers, telecommunications, sensing, and emerging AI hardware. A typical PIC design flow starts from physics-driven modeling (`FEM/FDTD`), proceeds through parameter sweeps and optimization, and ends with **photolithography mask** layout and fabrication-ready **`GDS`** generation. In the GDS, device geometry and layer assignments must be precise, manufacturable, and consistent with the foundry process design kit `(PDK)`.

Despite its maturity, the PIC design process remains labor-intensive. Many stages require expert time to translate requirements into geometry, verify constraints, and iterate. As a result, there is strong motivation to introduce **AI assistance**. Prior research has largely focused on **inverse-design** neural networks for one device or a narrow class of devices. These approaches lack generality and do not fundamentally improve productivity across the broader silicon photonics industry.

This course project, AutoGDS, is the first step of my undergraduate thesis. The long-term goal is a **multi-agent** PIC design helper: starting from **natural-language** requirements, agents would interpret specifications, run simulations, optimize performance metrics, decide geometry and parameters, and finally generate fabrication-ready `GDS` masks.

Currently, AutoGDS focuses on the last step of that vision: **given geometry and parameters expressed in natural language, the system uses agents to produce a concrete `GDS layout`**, potentially freeing engineers from their least favorite part of work.

This project currently contains about **12,158 lines of Python code** (excluding the PhIDO reference folder and virtual environments), and all API keys used for development and testing were **self-funded**.

## Project Structure
```
AutoGDS_v1/
├── src/                             # Source package (Python)
│   └── autogds/                     # Core pipeline modules
│       ├── cli.py                   # CLI entry point
│       ├── flow.py                  # End-to-end pipeline orchestration
│       ├── topology.py              # Topology planning logic
│       ├── layout_*.py              # Layout placement/routing/emission stages
│       ├── verify.py                # Verification checks
│       └── ...                      # Other pipeline utilities and schemas
├── KnowledgeBase/                   # Design knowledge and components
│   ├── DesignLibrary/               # Photonic component library
│   │   ├── mzi_2x2_heater_tin_cband.py  # Example MZI component
│   │   ├── _mmi1x2.py                # Example MMI splitter
│   │   └── ...                      # Other photonic components
│   ├── FDTD/                        # FDTD data assets
│   └── __init__.py                  # Package marker
├── docs/                            # Project documentation
│   ├── ARCHITECTURE.md              # Pipeline overview
│   ├── PROMPT_PATTERNS.md           # Prompt patterns and tips
│   └── TROUBLESHOOTING.md           # Troubleshooting guide
├── results/                         # Sample run outputs and figures
│   ├── Figures/                     # Figures used in README
│   ├── Level 1-1/                   # Level 1 example outputs
│   └── ...                          # Other level folders
├── GETTING_STARTED.md               # Tutorial and user guide
├── sample_prompts.md                # Prompt examples by difficulty level
├── requirements.txt                 # Minimal dependencies
├── pyproject.toml                   # Packaging and build config
└── README.md                        # This file (English version)
└── README_zh.md                     # This file (Chinese Version)
```

**For used guide, see `GETTING_STARTED.md`.**

## Implemented Functionality
AutoGDS currently implements an end-to-end, **force-output** flow: every run yields a complete artifact set even when constraints are imperfect. The pipeline is **components-only** and avoids templates, while still producing a concrete `GDS` when the layout backend is available.

What the system does:
- Parses a natural-language prompt into a structured `brief.json` with roles, counts, and wiring notes.
- Builds a topology graph (`topology_plan.json`) with required port forms and connection intents.
- Retrieves catalog components and ranks them using contract metadata (ports, labels, specs).
- Binds parameters and logical port mappings into a concrete `blueprint.json`.
- Emits layout artifacts (`layout_*.json`) and a final `layout.gds`.
- Produces verification reports without aborting the pipeline.

Example (splitter tree):
- Prompt: “Layout 1x2 MMIs connected to each other for a 1x8 splitter tree”.
- `brief.json` expands the request into **7 splitters** arranged as a **3‑stage binary tree**.
- `topology_plan.json` contains 7 nodes (`n0`–`n6`) and 6 links that form a 1‑2‑4 cascade.
- `selection.json` resolves each node to `_mmi1x2` from the design library.
- `blueprint.json` maps logical ports (`in0/out0/out1`) to physical ports (`o1/o2/o3`).
- `layout_emit.json` reports no issues and writes a non‑empty `layout.gds` (20 KB).

These artifacts provide full transparency: every decision, binding, and routing step can be inspected or replayed.

## Architecture and Methods
AutoGDS is designed as a **document-first pipeline**: each stage emits a typed JSON artifact that freezes the system state into a machine-readable contract. This choice is essential in photonics. Free-form text is not a reliable interface for geometry or port reasoning; structured schemas are. By enforcing explicit artifacts, AutoGDS becomes *explainable*, *auditable*, and *reproducible* across runs.

1) **Interpretation: Natural Language -> Structured Brief (AI agent)**
   - **Purpose:** convert human intent into a machine-actionable representation.
   - **Why structured JSON?** Photonic design depends on exact port counts, component roles, and constraints. A paragraph cannot be deterministically parsed downstream, while `DesignBrief` is a schema with explicit fields (roles, counts, wiring notes, objectives). This ensures every later step consumes unambiguous data.
   - **Method:** an LLM extracts and normalizes the prompt into `brief.json`. This file is the contract between the agent and the deterministic pipeline.

2) **Topology Planning: Abstract Graph Construction (deterministic)**
   - **Purpose:** translate the brief into a component graph before selecting any concrete device.
   - **Why a separate topology stage?** PIC design is a **network problem**, not a single-component problem. The topology stage defines the connectivity that must be preserved regardless of which exact component is chosen.
   - **Method:** rule-based parsing of port forms (`NxM`), port counts, and wiring notes. When the prompt implies a canonical structure (e.g., “splitter tree”), the planner instantiates a graph template such as a binary tree.
   - **Artifact:** `topology_plan.json` encodes nodes, intents, and top-level ports.

3) **Component Retrieval & Selection: Candidate Ranking (AI-assisted)**
   - **Purpose:** bind each abstract node to a real component from the library.
   - **Why AI here?** Catalog metadata is semi-structured. The “best” component is often a semantic match, not a direct string match.
   - **Method:** text-similarity ranking over docstrings, followed by **contract-aware re-ranking** (port-form match, label/spec hits, argument compatibility).
   - **Artifacts:** `options_node_*.json` (ranked candidates) and `selection.json` (final choices), making selection transparent and reproducible.

    📚**DesignLibrary and its provenance.** AutoGDS relies on a curated `DesignLibrary` of parameterized photonic components. The library is treated as a catalog with machine-readable docstrings (ports, labels, specs, arguments), enabling both semantic retrieval and deterministic binding. This approach follows the component-knowledge organization described in *APL Mach. Learn. 3, 046113 (2025)*, and we explicitly acknowledge that the library structure and documentation style are derived from that work.

4) **Binding: Parameters and Ports (deterministic with AI-extracted hints)**
   - **Purpose:** resolve logical ports and parameters into a concrete design.
   - **Method:** map logical ports (`in0/out0`) to physical ports (`o1/o2/...`) using `ComponentContract`. Parse numeric constraints from notes (units, synonyms such as `delta_length`) and validate against component signatures.
   - **Artifact:** `blueprint.json` with resolved ports, parameters, and links.

5) **Verification: Structural Integrity Checks (deterministic)**
   - **Purpose:** preserve force-output while still exposing issues.
   - **Method:** check missing ports, invalid links, and mapping conflicts. Errors are recorded but the pipeline continues.
   - **Artifact:** `verify_report.json` for debugging and iteration.

6) **Layout Synthesis: Geometry and GDS (deterministic)**
   - **Purpose:** translate the blueprint into physical geometry.
   - **Method:** footprint estimation -> placement -> routing -> precheck -> GDS emission.
   - **Algorithms:** layered placement by graph depth, Manhattan routing with collision-aware detours, and a gdsfactory-based backend for final `layout.gds`.
   - **Artifacts:** `layout_*.json` plus the final `layout.gds`.

This architecture ensures AI is applied where ambiguity exists (interpretation and semantic selection), while the remaining stages are deterministic, inspectable, and repeatable.

## Results
1) **Prompt Classification**

    To help characterize the performance of AutoGDS, we classify prompts into four levels based on complexity:
    
    - **Level 1:** 1 component

    - **Level 2:** 2 components with a single connecting edge

    - **Level 3:** 3-10 components

    - **Level 4**: 10+ components

    In ``sample_prompts.md``, four sample prompts are given for each level. Their running results are given in the `results` folder.
2) **Running example**
    
    We use a level 3 prompt to illustrate the workflow:

    `Four microrings with heaters, arranged in an array along the y direction, each connected to a grating coupler.`
    - Start AutoGDS in the virtual environment and enter the prompt

   ![Running example prompt](results/Figures/Fig1.png)

    - Select preferred components from the list

    ![Running example prompt](results/Figures/Fig2.png)
    ![Running example prompt](results/Figures/Fig3.png)

    - Output folder and artifacts are returned

    ![Running example prompt](results/Figures/Fig4.png)

    - Open the folder in file explorer and check the GDS file in  `KLayout`

    ![Running example prompt](results/Figures/Fig5.png)

3) **Sample prompt results**  
- Level 1: single component

   `A 2x2 MZI.`

   ![Running example prompt](results/Figures/1-1.png)

   `A four-channel WDM.`

   ![Running example prompt](results/Figures/1-2.png)

   `Directional coupler with a 0.5um gap and 50um coupling length.`

   ![Running example prompt](results/Figures/1-3.png)

   `A microring with coupler and heater.`

   ![Running example prompt](results/Figures/1-4.png)

- Level 2: two components with a single connecting edge

   `Two cascaded MZIs, each with TiN heaters for C-band operation. The device should have 500 nm wide waveguides and 10 um long heaters. Both MZIs have two input/output ports.`

   ![Running example prompt](results/Figures/2-1.png)

   `Connect a 2x2 MZI with heaters to a grating coupler. Port 1 to port 0.`

   ![Running example prompt](results/Figures/2-2.png)

   `Connect a 2x2 MZI with heaters to a grating coupler. Port 0 to port 0.`

   ![Running example prompt](results/Figures/2-3.png)

   `Connect a 1x2 splitter to a 1x1 microring resonator.`

   ![Running example prompt](results/Figures/2-4.png)
    
- Level 3: 3-10 components

   `Layout 1x2 MMIs connected to each other to for a 1x8 splitter tree.`

   ![Running example prompt](results/Figures/3-1.png)
   
   `A power splitter connected to two 1*1 MZIs with doped heaters each with a path difference 100 um. The two output ports of the splitter are the input ports of the two MZIs respectively.`

   ![Running example prompt](results/Figures/3-2.png)

   `Eight low loss and low power thermo optic phase shifters. The phase shifters should be arranged in parallel along the y direction in an array.`

   ![Running example prompt](results/Figures/3-3.png)

   `Four microrings with heaters, arranged in an array along the y direction, each connected to a grating coupler.`

   ![Running example prompt](results/Figures/3-4.png)

- Level 4: 10+ components

   `A 1x16 splitter tree built from 1x2 MMIs.`

   ![Running example prompt](results/Figures/4-1.png)

   `A 3x4 mesh of 2x2 MZIs with back‑to‑back connections between adjacent nodes.`

   ![Running example prompt](results/Figures/4-2.png)

   `Sixteen thermo‑optic phase shifters arranged in a 4x4 mesh.`

   ![Running example prompt](results/Figures/4-3.png)

   `A 1x8 splitter tree using 1x2 MMIs, and connect each output to a grating coupler.`

   ![Running example prompt](results/Figures/4-4.png)

4) **Repeatability test**

To test the repeatability of the workflow, we ran 10 tests on each of the 16 sample prompts, and computed design accuracy and analyzed sources of errors.

- **Accuracy**

| Level \ No. | 1 | 2 | 3 | 4 |
|---:|---:|---:|---:|---:|
| 1 | 0.5 | 0.6 | 0.7 | 1.0 |
| 2 | 0.9 | 1.0 | 1.0 | 1.0 |
| 3 | 0.8 | 0.5 | 1.0 | 0.7 |
| 4 | 0.9 | 0.9 | 1.0 | 0.0 |

![Running example prompt](results/Figures/Fig6.png)

Accuracy does not show a clear decreasing trend with increasing complexity level, which indicates the scaling effect is not significant. 

Total accuracy is **84.4%**, and in each case, accuracy is no less than 50%, showing fairly good reproducibility.

- **Error sources**

![Running example prompt](results/Figures/Fig7.png)

Three types of errors exist:

   *Component identification error* (9%): Target components are not included in the selection list, or extra or insufficient components are asked.

   *Parameter assignment error* (5%): Incorrect parameters are assigned, usually because parameter requirements in the prompt fail to be captured, and default parameter values are used.

   *Topology layout* (1%): Device topology is incorrect, either spatial layout or port relationships.

These errors reflect where ambiguity still leaks into the pipeline. Component identification errors typically occur when the library vocabulary is incomplete or when prompts use synonyms that are not present in docstrings, so semantic retrieval cannot anchor the intent. The practical solution is to expand alias coverage in component metadata, strengthen role-specific filters, and add a lightweight user confirmation step when top candidates have close scores.

Parameter assignment errors stem from natural-language constraints that are embedded in prose, expressed with mixed units, or described with synonyms (e.g., “differential path length”). A robust solution is to normalize units aggressively, maintain per-component parameter schemas, and provide a short structured clause option (e.g., `delta_length=100um`) when precision is required.

Topology layout errors are rare but high-impact because a single wrong connection can invalidate the circuit. These errors usually arise from ambiguous words like “cascade,” “mesh,” or “array,” and from inconsistent port-order conventions across components. The solution is to formalize topology templates, make port-order rules explicit, and validate the graph against required port forms before layout so incorrect wiring is caught early.

Due to limited API budget, I did not perform further optimization and re-tests.

## Outlook and Improvements
AutoGDS can become more reliable by adding a **real-time interactive loop** where users can correct the pipeline when it makes a mistake. In practice, this means exposing intermediate artifacts (`brief.json`, `topology_plan.json`, `selection.json`, and `blueprint.json`) in a UI, letting users edit or confirm them, and resuming the run from that checkpoint. Allowing users to correct errors as they happen will directly increase success rate and reduce wasted reruns.

Another near-term improvement is a **stronger constraint system** for ports, parameters, and units. Today, many fixes rely on heuristics; a declarative constraint layer could validate ranges, enforce unit compatibility, and reject ambiguous bindings before layout. This would prevent silent errors such as wrong heater lengths or mismatched port forms.

AutoGDS would also benefit from **layout-aware topology planning**. The planner could use rough footprint estimates and routing cost models to choose between equivalent graph structures (e.g., balanced vs. skewed trees), avoiding downstream routing failures. This makes topology decisions sensitive to geometric feasibility rather than purely textual intent.

The **DesignLibrary coverage** should be expanded and normalized. Adding more parameterized building blocks (e.g., modulators, detectors, filters) and standardizing their docstrings will increase component recall and improve selection quality. A curated, versioned library with unit tests for each component would further stabilize the pipeline.

Another improvement is to adopt **progressive refinement** for routing. A fast initial routing pass could identify clashes, then selectively re-route only problematic connections with detours or lane assignment. This would be more robust than a single-shot Manhattan route and would better scale to larger graphs.

Finally, AutoGDS should add **automatic evaluation and benchmarking**. A standard prompt suite with pass/fail criteria (non-empty GDS, correct port counts, no crossings) would quantify progress over time. Coupled with regression tests, this would prevent improvements in one area from breaking others.

Beyond these near-term improvements, for my undergraduate thesis, I wish to deliver a **full-process photonics design agent** that covers the full workflow of device simulation and layout. It can be realized by chaining simulation, optimization, and layout into a single goal-driven loop. The agent would interpret a natural-language spec, choose a parametric template, run fast surrogate simulations (or reduced-order models) to evaluate performance metrics, and iteratively update geometry with a constrained optimizer before emitting GDS. Integrating these stages allows the system to reason about **performance and manufacturability jointly**, reducing trial-and-error and enabling rapid exploration of design trade-offs. The benefit is a single, accountable pipeline that turns high-level intent into validated, fabrication-ready layouts, significantly lowering the expertise barrier for photonics design.

I would need funding source and a team to pursue this goal, and I'm leaving this to after the course deadline. Do something big!
