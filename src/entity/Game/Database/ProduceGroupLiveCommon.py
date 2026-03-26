"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass(slots=True)
class ProduceGroupLiveCommon:
    characterId: str = None
    produceGroupId: str = None
    type: str = None
    musicId: str = None
    needForceLiveCommonIdolCard: bool = None
    unlockConditionSetId: str = None
    thumbnailAssetId: str = None
    environmentAssetId: str = None
    timelineAssetId: str = None
    motionAssetIds: List[str] = field(default_factory=list)
    liveMusicAssetId: str = None
    beforeAdvAssetId: str = None
    afterAdvAssetId: str = None
    liveOverrideAssetId: str = None
    additionalActorAssetIds: List[Any] = field(default_factory=list)
