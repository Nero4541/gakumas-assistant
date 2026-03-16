"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class ProduceDescriptionLabelProduceDescriptionsItem:
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
class ProduceDescriptionLabel:
    id: str = None
    name: str = None
    produceDescriptionSwapId: str = None
    produceDescriptions: List[ProduceDescriptionLabelProduceDescriptionsItem] = field(default_factory=list)
    localization: ProduceDescriptionLabelLocalization = None

@dataclass
class ProduceDescriptionLabelLocalization:
    id: str = None
    produceDescriptions: List[Any] = field(default_factory=list)
    name: str = None
