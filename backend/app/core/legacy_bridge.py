from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any


LEGACY_SCRIPTS = Path("/Users/hehai/Documents/开目软件/Agents/skills/paper-generation/scripts")


@lru_cache(maxsize=1)
def load_legacy_mentor_fit():
    if not LEGACY_SCRIPTS.exists():
        return None
    if str(LEGACY_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(LEGACY_SCRIPTS))
    try:
        from paper_generation_lib.mentor_fit import build_mentor_fit  # type: ignore

        return build_mentor_fit
    except Exception:
        return None


def build_mentor_fit(project: dict[str, Any], intake: list[dict[str, Any]]) -> dict[str, Any]:
    loader = load_legacy_mentor_fit()
    if not loader:
        return {
            "preferences": [],
            "scores": [],
            "recommended_theories": [],
            "risk_alerts": [],
        }
    return loader(project, intake)
