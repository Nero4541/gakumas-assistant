"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class ProducerLevelUnlockTargetsItem:
    type: str = None
    id: str = None
    quantity: int = None

@dataclass
class ProducerLevelReward:
    resourceType: str = None
    resourceId: str = None
    quantity: int = None

@dataclass
class ProducerLevel:
    level: int = None
    totalExp: int = None
    unlockTargets: List[ProducerLevelUnlockTargetsItem] = field(default_factory=list)
    reward: ProducerLevelReward = None
    bonusRewards: List[Any] = field(default_factory=list)
