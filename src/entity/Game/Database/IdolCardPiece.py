"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class IdolCardPieceExchangeReward:
    resourceType: str = None
    resourceId: str = None
    quantity: int = None

@dataclass
class IdolCardPiece:
    idolCardId: str = None
    itemId: str = None
    releaseConsumptionQuantity: int = None
    exchangeReward: IdolCardPieceExchangeReward = None
