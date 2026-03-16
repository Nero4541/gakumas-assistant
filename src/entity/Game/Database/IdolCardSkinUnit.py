"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class IdolCardSkinUnit:
    id: str = None
    idolCardSkinIds: List[str] = field(default_factory=list)
    unitCharacters: List[Any] = field(default_factory=list)
    liveOrderCharacterIds: List[str] = field(default_factory=list)
