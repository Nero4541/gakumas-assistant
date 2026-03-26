"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass(slots=True)
class MemoryGiftProduceCard:
    id: str = None
    upgradeCount: int = None
    customizes: List[Any] = field(default_factory=list)

@dataclass(slots=True)
class MemoryGiftMemoryAbilitiesItem:
    id: str = None
    level: int = None

@dataclass(slots=True)
class MemoryGiftExamBattleProduceCardsItem:
    id: str = None
    upgradeCount: int = None
    customizes: List[Any] = field(default_factory=list)

@dataclass(slots=True)
class MemoryGift:
    id: str = None
    name: str = None
    description: str = None
    assetId: str = None
    grade: str = None
    idolCardId: str = None
    planType: str = None
    produceCard: MemoryGiftProduceCard = None
    produceCardPhaseType: str = None
    memoryAbilities: List[MemoryGiftMemoryAbilitiesItem] = field(default_factory=list)
    vocal: int = None
    dance: int = None
    visual: int = None
    stamina: int = None
    examBattleProduceCards: List[MemoryGiftExamBattleProduceCardsItem] = field(default_factory=list)
    examBattleProduceItemIds: List[str] = field(default_factory=list)
    localization: MemoryGiftLocalization = None

@dataclass(slots=True)
class MemoryGiftLocalization:
    id: str = None
    name: str = None
