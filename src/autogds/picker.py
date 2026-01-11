from __future__ import annotations

from typing import Dict, List, Tuple
from rich.console import Console
from rich.table import Table

from autogds.schema import Option

console = Console()


def choose_option(
    title: str,
    options: List[Option],
    non_interactive: bool,
    default_index: int = 0,
) -> Tuple[Option, Dict[str, object]]:
    if not options:
        raise ValueError(f"No options provided for {title}")

    default_index = max(0, min(default_index, len(options) - 1))

    if non_interactive:
        picked = options[default_index]
        meta = {"mode": "non_interactive", "user_input": None, "selected_index": default_index}
        return picked, meta

    table = Table(title=title, show_lines=False)
    table.add_column("#", justify="right")
    table.add_column("symbol", overflow="fold")
    table.add_column("score", justify="right")
    table.add_column("rationale", overflow="fold")

    for i, opt in enumerate(options):
        table.add_row(str(i), opt.symbol, f"{opt.score:.3f}", opt.rationale)

    console.print(table)

    while True:
        raw = console.input(f"Select [0-{len(options)-1}] (default {default_index}): ")
        user_input = raw  # keep original
        raw = raw.strip()

        if raw == "":
            meta = {"mode": "interactive", "user_input": user_input, "selected_index": default_index}
            return options[default_index], meta

        if raw.isdigit():
            idx = int(raw)
            if 0 <= idx < len(options):
                meta = {"mode": "interactive", "user_input": user_input, "selected_index": idx}
                return options[idx], meta

        console.print("Invalid selection. Please enter a valid number.")
