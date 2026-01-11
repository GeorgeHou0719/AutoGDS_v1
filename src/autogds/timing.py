from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator, Optional


@contextmanager
def timed() -> Iterator[callable]:
    start = time.perf_counter()

    def elapsed_ms() -> int:
        return int((time.perf_counter() - start) * 1000)

    yield elapsed_ms
