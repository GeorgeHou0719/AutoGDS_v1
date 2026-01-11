from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable

import numpy as np


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "KnowledgeBase").exists():
            return parent
    return here.parents[2]


def get_file_path(rel_path: str) -> str:
    root = _repo_root()
    parts = [p for p in rel_path.replace("\\", "/").split("/") if p]
    return str((root / "KnowledgeBase" / Path(*parts)).resolve())


def model_from_npz(filepath: str, xkey: str = "wavelengths", xunits: float = 1.0):
    sp = np.load(filepath)
    keys = list(sp.keys())
    if xkey not in keys:
        raise ValueError(f"{xkey!r} not in {keys}")

    x = np.asarray(sp[xkey] * xunits)
    idxs = np.argsort(x)
    x = x[idxs]

    series = {}
    for k in keys:
        if k == xkey:
            continue
        series[k] = np.asarray(sp[k])[idxs]

    def model(wl: Iterable[float] | np.ndarray):
        wl_arr = np.asarray(wl, dtype=float)
        out: Dict[tuple[str, str], np.ndarray] = {}
        for key, vals in series.items():
            if "," not in key or "@" not in key:
                continue
            port_mode0, port_mode1 = key.split(",", 1)
            port0 = port_mode0.split("@", 1)[0]
            port1 = port_mode1.split("@", 1)[0]
            mag = np.interp(wl_arr, x, np.abs(vals))
            phase = np.interp(wl_arr, x, np.unwrap(np.angle(vals)))
            out[(port0, port1)] = mag * np.exp(1j * phase)
        return out

    return model
