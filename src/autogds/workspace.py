from __future__ import annotations
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import secrets

def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p

def new_run_tag() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    rnd = secrets.token_hex(3)
    return f"{ts}_{rnd}"

@dataclass(frozen=True)
class RunWorkspace:
    root: Path

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def catalog(self) -> Path:
        return self.root / "catalog"

def create_workspace(base_dir: str) -> RunWorkspace:
    base = _ensure_dir(Path(base_dir))
    tag = new_run_tag()
    root = _ensure_dir(base / tag)
    _ensure_dir(root / "raw")
    _ensure_dir(root / "catalog")
    return RunWorkspace(root=root)

def write_text(path: Path, text: str) -> None:
    _ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")

def write_json(path: Path, obj) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
