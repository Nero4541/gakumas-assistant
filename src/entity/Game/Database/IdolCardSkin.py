"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass(slots=True)
class IdolCardSkin:
    id: str = None
    idolCardId: str = None
    name: str = None
    assetId: str = None
    costumeHeadId: str = None
    costumeId: str = None
    musicId: str = None
    idolCardSsrAnimationStartMilliseconds: int = None
    additionalCostumeHeadIds: List[str] = field(default_factory=list)
    additionalCostumeIds: List[Any] = field(default_factory=list)
    homeVoiceGroupId: str = None
    detailVoiceGroupId: str = None
    beforeLevelLimitRankVoiceAssetId: str = None
    afterLevelLimitRankVoiceAssetId: str = None
    produceSelectVoiceAssetId: str = None
    produceSelectFacialAssetId: str = None
    produceSelectBodyAssetId: str = None
    produceScheduleVoiceGroupId: str = None
    levelLimitRank7VoiceAssetId: str = None
    hasProduceIdolAnimation: bool = None
    hasGashaAnimation: bool = None
    isProduceIdolAnimationStillCard: bool = None
    beforeListPositionX: int = None
    beforeListPositionY: float = None
    beforeListScale: int = None
    afterListPositionX: int = None
    afterListPositionY: float = None
    afterListScale: int = None
    beforeDetailPositionX: float = None
    beforeDetailPositionY: float = None
    beforeDetailScale: int = None
    afterDetailPositionX: float = None
    afterDetailPositionY: float = None
    afterDetailScale: int = None
    beforeLevelLimitRankPositionPattern: int = None
    afterLevelLimitRankPositionPattern: int = None
    viewStartTime: str = None
    order: str = None
