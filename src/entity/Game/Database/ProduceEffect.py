"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class ProduceEffectProduceRewardsItem:
    resourceType: str = None
    resourceId: str = None
    resourceLevel: int = None

@dataclass
class ProduceEffect:
    id: str = None
    produceEffectType: Any = None
    effectValueMin: int = None
    effectValueMax: int = None
    produceResourceType: str = None
    produceRewards: List[ProduceEffectProduceRewardsItem] = field(default_factory=list)
    produceCardSearchId: str = None
    produceExamStatusEnchantId: str = None
    produceStepEventDetailId: str = None
    pickRangeType: str = None
    pickCountMin: int = None
    pickCountMax: int = None
    isResearch: bool = None
