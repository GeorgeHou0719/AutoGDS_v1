from __future__ import annotations

import difflib
import re
from typing import List, Tuple

from autogds.schema import CatalogEntry, Option


def _normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _best_snippet(text: str, keywords: List[str], max_len: int = 140) -> str:
    t = " ".join(text.split())
    if not t:
        return ""

    # 找到第一个命中的关键词位置附近截断
    lt = t.lower()
    for kw in keywords:
        i = lt.find(kw)
        if i >= 0:
            start = max(0, i - 40)
            end = min(len(t), i + 80)
            snippet = t[start:end]
            return snippet[:max_len]

    return t[:max_len]


def rank_catalog(query: str, catalog: List[CatalogEntry], top_k: int = 12) -> List[Option]:
    q = _normalize(query)
    q_tokens = [t for t in re.split(r"[^a-z0-9_]+", q) if t]

    scored: List[Tuple[float, CatalogEntry]] = []

    for e in catalog:
        hay = _normalize(e.symbol + " " + e.doc)
        sim = difflib.SequenceMatcher(a=q, b=hay[:4000]).ratio()  # 限长避免过慢

        # 关键词命中加分（简单且有效）
        hits = sum(1 for t in q_tokens if t in hay)
        score = sim + 0.08 * min(hits, 6)

        if score > 0.10:  # 过滤非常不相关的
            scored.append((score, e))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    opts: List[Option] = []
    for s, e in top:
        rationale = _best_snippet(e.doc, q_tokens) or "Matched by name/doc similarity"
        opts.append(Option(symbol=e.symbol, source_file=e.source_file, score=float(s), rationale=rationale))

    return opts
