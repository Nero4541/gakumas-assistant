"""producer_challenge 的 LLM prompt 渲染层。"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import jinja2


_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


@functools.lru_cache(maxsize=1)
def _get_env() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_PROMPT_DIR)),
        keep_trailing_newline=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render(template_name: str, **kwargs: Any) -> str:
    return _get_env().get_template(template_name).render(**kwargs)
