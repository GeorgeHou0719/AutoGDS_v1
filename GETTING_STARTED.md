# Installation and Run Guide

This guide provides step-by-step instructions to install and run AutoGDS.

## 1) Prerequisites
- Windows 10/11.
- Python 3.10+.
- A terminal (PowerShell recommended on Windows).
- KLayout software (to view GDS, not required in the project workflow). 
    - Download link: https://www.klayout.de/builds/klayout-0.28.17-win64.exe
- VPN for users in Chinese Mainland

## 2) Create a Virtual Environment
From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\.venv\Scripts\Activate.ps1
```

## 3) Install Dependencies
Install core dependencies:

```powershell
pip install -r requirements.txt
```

Install layout extras (needed for real GDS generation):

```powershell
pip install ".[layout]"
```

## 4) Configure API Key
AutoGDS uses the OpenAI API for prompt parsing. Only OpenAI APIs and models are supported.

Create a `.env` file in the project root:

```text
OPENAI_API_KEY=your_key_here
AUTOGDS_MODEL=your_model_here
```

Recommended models:
- gpt-5.2 (cheap and fairly powerful)
- o3-pro (best quality for complex reasoning and long chains of constraints)
- o3 (strong reasoning at lower cost than o3-pro)
- gpt-4o (cheap, balanced general performance and speed)
- gpt-4o-mini (fast, lowest cost for simple prompts)

For more information on APIs and models, visit https://platform.openai.com/settings/.

## 5) Run a Prompt (CLI)
Use the guided UI:

```powershell
autogds ui
```

Then enter your request. After this, you will be guided to select preferred components from a list. When you make your selection, AutoGDS will automatically perform layout and routing and create the gds file.

See `docs\PROMPT_PATTERNS.md` for instrutions on writing prompts.

## 6) Output Files
Each run writes to a new folder under `runs\`.
Key files:
- `brief.json`: parsed prompt.
- `topology_plan.json`: component graph.
- `selection.json`: selected components.
- `blueprint.json`: bound design.
- `layout_*.json`: layout stages.
- `layout.gds`: final GDS (if gdsfactory installed).


## 7) Common Issues
- If `layout.gds` is empty, check `layout_emit.json` for errors.
- If selection is wrong, inspect `options_node_*.json` to see candidate ranking.
- If params are ignored, ensure units are explicit (e.g., `100 um`).
