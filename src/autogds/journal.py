from __future__ import annotations
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

@dataclass
class RunJournal:
    path: Path

    def log(
        self,
        area: str,
        event: str,
        note: str = "",
        artifacts: Optional[Dict[str, str]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        rec = {
            "ts_ms": int(time.time() * 1000),
            "area": area,
            "event": event,
            "note": note,
            "artifacts": artifacts or {},
            "extra": extra or {},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
