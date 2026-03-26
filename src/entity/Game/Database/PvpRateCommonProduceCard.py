"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass(slots=True)
class PvpRateCommonProduceCardProduceCardsItem:
    id: str = None
    upgradeCount: int = None
    customizes: List[Any] = field(default_factory=list)

@dataclass(slots=True)
class PvpRateCommonProduceCard:
    id: str = None
    planType: str = None
    produceCards: List[PvpRateCommonProduceCardProduceCardsItem] = field(default_factory=list)
