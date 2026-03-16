"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class ProduceStepEventDetailProduceDescriptionsItem:
    produceDescriptionType: str = None
    examDescriptionType: str = None
    examEffectType: str = None
    produceCardGrowEffectType: str = None
    produceCardCategory: str = None
    produceCardMovePositionType: str = None
    produceStepType: str = None
    produceStepBusinessType: str = None
    text: str = None
    targetId: str = None
    targetLevel: int = None
    effectValue1: int = None
    effectValue2: int = None
    effectCount: int = None
    turn: int = None
    costValue: int = None
    produceDescriptionSwapId: str = None
    originProduceExamTriggerId: str = None
    originProduceExamEffectId: str = None
    originProduceCardStatusEnchantId: str = None
    isCost: bool = None
    isOnlyOutGame: bool = None
    changeColor: bool = None

@dataclass
class ProduceStepEventDetail:
    id: str = None
    suggestionType: str = None
    produceStoryId: str = None
    produceStoryGroupId: str = None
    produceEffectIds: List[str] = field(default_factory=list)
    produceStepEventSuggestionIds: List[str] = field(default_factory=list)
    supportCardId: str = None
    eventType: str = None
    eventCharacterType: str = None
    isBusinessExcellent: bool = None
    produceDescriptions: List[ProduceStepEventDetailProduceDescriptionsItem] = field(default_factory=list)
    localization: ProduceStepEventDetailLocalization = None

@dataclass
class ProduceStepEventDetailLocalization:
    id: str = None
    produceDescriptions: List[Any] = field(default_factory=list)
