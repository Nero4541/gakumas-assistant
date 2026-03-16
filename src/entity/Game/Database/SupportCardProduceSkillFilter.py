"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class SupportCardProduceSkillFilter:
    id: str = None
    title: str = None
    order: int = None
    produceEffectTypes: List[str] = field(default_factory=list)
    produceTriggerIds: List[str] = field(default_factory=list)
    localization: SupportCardProduceSkillFilterLocalization = None

@dataclass
class SupportCardProduceSkillFilterLocalization:
    id: str = None
    order: int = None
    title: str = None
