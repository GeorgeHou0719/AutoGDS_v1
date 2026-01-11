from __future__ import annotations

import os
from dataclasses import dataclass

from openai import OpenAI

from autogds.schema import DesignBrief


@dataclass(frozen=True)
class BriefMakerConfig:
    model: str


class BriefMakerError(RuntimeError):
    pass


def build_brief(request_text: str, cfg: BriefMakerConfig) -> tuple[DesignBrief, str]:
    """
    Returns:
      - brief: validated DesignBrief (Structured Outputs)
      - raw_text: model output text (debug)
    """
    client = OpenAI()  # reads OPENAI_API_KEY from environment

    system = (
        "You are AutoGDS brief generator. "
        "Return a DesignBrief that is implementable with photonic building blocks. "
        "If a field is not specified, set it to null or an empty list as appropriate. "
        "Do NOT split integrated subcomponents into separate blocks. "
        "If a component is integrated into another (e.g., heaters in an MZI), "
        "keep it inside the parent block's notes/specs and do not create a separate BlockHint."
    )

    user = (
        "Convert the following request into a DesignBrief.\n"
        f"Request:\n{request_text}"
    )

    try:
        resp = client.responses.parse(
            model=cfg.model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            text_format=DesignBrief,
        )
    except Exception as e:
        raise BriefMakerError(f"OpenAI call failed: {e}") from e

    raw_text = getattr(resp, "output_text", "") or ""
    brief = getattr(resp, "output_parsed", None)

    if brief is None:
        raise BriefMakerError("No output_parsed returned (schema enforcement failed).")

    # 确保 schema_rev 一定存在（你的管线默认 r1）
    if not brief.schema_rev:
        brief.schema_rev = "r1"
    brief.schema_rev = "r1"

    return brief, raw_text
