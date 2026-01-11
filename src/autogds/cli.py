from __future__ import annotations

import argparse
from rich.console import Console

from autogds import __version__ as autogds_version
from autogds.workspace import create_workspace, write_json
from autogds.journal import RunJournal
from autogds.schema import DesignBrief, BlockHint
from autogds.flow import run_skeleton
from pathlib import Path

import os
from dotenv import load_dotenv, find_dotenv

from autogds.brief_maker import BriefMakerConfig, BriefMakerError, build_brief
from autogds.workspace import write_text


console = Console()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="autogds")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Generate layout artifacts from a natural-language request")
    run.add_argument("request", type=str, help="Natural language request")
    run.add_argument("--out", type=str, default="runs", help="Output directory for run artifacts")
    run.add_argument("--non-interactive", action="store_true", help="Disable interactive selection")
    run.add_argument("--catalog", type=str, required=True, help="Path to a Python component library to scan")

    ui = sub.add_parser("ui", help="Interactive prompt for running AutoGDS")
    ui.add_argument("--out", type=str, default="runs", help="Output directory for run artifacts")
    ui.add_argument("--non-interactive", action="store_true", help="Disable interactive selection")
    ui.add_argument("--catalog", type=str, default=".\\KnowledgeBase\\DesignLibrary\\", help="Path to a Python component library to scan")
    return p


def main() -> None:
    args = build_parser().parse_args()

    if args.cmd not in {"run", "ui"}:
        raise SystemExit(2)

    load_dotenv(find_dotenv(), override=False)

    if args.cmd == "ui":
        console.print("[bold]AutoGDS interactive mode[/bold]")
        req = console.input("Enter request: ").strip()
        if not req:
            raise SystemExit("Request is required.")
        args.request = req

    ws = create_workspace(args.out)
    jr = RunJournal(ws.root / "journal.jsonl")

    jr.log("cli", "start", note="run started", extra={"request": args.request})

    write_json(
        ws.root / "run.json",
        {
            "project": "AutoGDS",
            "autogds_version": autogds_version,
            "schema_rev": "r1",
            "request": args.request,
            "out": args.out,
            "non_interactive": args.non_interactive,
        },
    )
    jr.log("run", "saved", artifacts={"run": str(ws.root / "run.json")})

    model = os.getenv("AUTOGDS_MODEL", "gpt-5.2").strip()
    cfg = BriefMakerConfig(model=model)

    try:
        brief, raw_text = build_brief(args.request, cfg)
    except BriefMakerError as e:
        jr.log("brief", "error", note=str(e))
        raise

    write_text(ws.raw / "brief_llm.txt", raw_text)

    brief_path = ws.root / "brief.json"
    write_json(brief_path, brief.model_dump())
    jr.log(
        "brief",
        "parsed",
        artifacts={"brief": str(brief_path), "raw_text": str(ws.raw / "brief_llm.txt")},
        extra={"model": model},
    )


    artifacts = run_skeleton(brief=brief,ws=ws,jr=jr,non_interactive=args.non_interactive,catalog_root=Path(args.catalog))

    console.print("\nArtifacts:")
    for k in sorted(artifacts.keys()):
        console.print(f"  - {k}: {artifacts[k]}")

    jr.log("cli", "end", note="workspace initialized", artifacts={"workspace": str(ws.root)})

    console.print(f"Workspace: {ws.root}")
