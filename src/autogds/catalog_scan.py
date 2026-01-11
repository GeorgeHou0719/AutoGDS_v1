from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable, List

from autogds.schema import CatalogEntry
from autogds.contract_extract import extract_contract

def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def scan_python_catalog(root: Path) -> List[CatalogEntry]:
    root = root.resolve()
    entries: List[CatalogEntry] = []

    for py in root.rglob("*.py"):
        # 跳过常见无意义文件
        if py.name == "__init__.py":
            continue
        if py.parts and any(p in {"__pycache__", ".venv", "venv", "build", "dist"} for p in py.parts):
            continue

        try:
            src = _read_text(py)
            tree = ast.parse(src)
        except Exception:
            continue

        mod = ".".join(py.relative_to(root).with_suffix("").parts)

        # module docstring
        mdoc = ast.get_docstring(tree)
        if mdoc and mdoc.strip():
            try:
                contract = extract_contract(py, preferred_symbol=None)
            except Exception:
                contract = None
            entries.append(CatalogEntry(symbol=f"{mod}", source_file=str(py), doc=mdoc.strip(), contract=contract))

        # class/function docstrings
        for node in tree.body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                d = ast.get_docstring(node)
                if d and d.strip():
                    sym = f"{mod}:{node.name}"
                    try:
                        contract = extract_contract(py, preferred_symbol=node.name)
                    except Exception:
                        contract = None
                    entries.append(CatalogEntry(symbol=sym, source_file=str(py), doc=d.strip(), contract=contract))


    return entries
