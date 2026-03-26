"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass(slots=True)
class CharacterProduceStory:
    characterId: str = None
    produceGroupId: str = None
    eventCharacterProduceStoryIds: List[str] = field(default_factory=list)
    eventCharacterGrowthProduceStoryIds: List[str] = field(default_factory=list)
    eventCampaignProduceStoryIds: List[Any] = field(default_factory=list)
    eventActivityProduceStoryIds: List[str] = field(default_factory=list)
    eventSchoolProduceStoryIds: List[str] = field(default_factory=list)
    eventBusinessProduceStoryIds: List[str] = field(default_factory=list)
