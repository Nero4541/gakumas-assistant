"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class CharacterTrueEndAchievementTrueEndAchievement:
    id: str = None
    threshold: int = None

@dataclass
class CharacterTrueEndAchievementTargetAchievementsItem:
    id: str = None
    threshold: int = None

@dataclass
class CharacterTrueEndAchievement:
    characterId: str = None
    produceType: str = None
    trueEndAchievement: CharacterTrueEndAchievementTrueEndAchievement = None
    targetAchievements: List[CharacterTrueEndAchievementTargetAchievementsItem] = field(default_factory=list)
