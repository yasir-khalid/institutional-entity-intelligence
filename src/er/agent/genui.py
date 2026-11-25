"""Generative UI for research answers (OpenUI Lang, https://www.openui.com).

The prompt section is generated from the web app's component spec
(web/scripts/openui-prompt.mjs -> config/openui/system-prompt.md), so the model
is only taught components the workspace can render. A block is part of the
answer text, so er.agent.facts gates it like prose: every value in it is a
fact placeholder the submission gate renders, never a number the model typed.
"""

from __future__ import annotations

import re
from functools import lru_cache

from er.config import REPO_ROOT, AppConfig

PROMPT_PATH = REPO_ROOT / "config" / "openui" / "system-prompt.md"
VISUAL = re.compile(r"\b(chart|graph|plot|visuali[sz]e|table|compare|comparison|trend|breakdown|over time)\b", re.I)


@lru_cache(maxsize=1)
def _prompt_text() -> str:
    text = PROMPT_PATH.read_text()
    return text.split("-->", 1)[1].strip() if text.startswith("<!--") else text


def prompt_section(cfg: AppConfig) -> str:
    if not cfg.agent.generative_ui or not PROMPT_PATH.exists():
        return ""
    return "\n\n## Visualizations (optional)\n" + _prompt_text()


def visual_hint(cfg: AppConfig, question: str) -> str:
    """A reminder appended to the user's turn when they asked for a visual -
    an optional prompt section alone is followed unreliably."""
    if not prompt_section(cfg) or not VISUAL.search(question):
        return ""
    return ("\n(This question asks for a visual: end your submitted answer with one ```openui-lang block "
            "whose values are fact placeholders, as described under Visualizations.)")
