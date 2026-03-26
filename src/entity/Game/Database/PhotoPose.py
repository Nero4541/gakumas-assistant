"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass(slots=True)
class PhotoPose:
    id: str = None
    photoBackgroundId: str = None
    cameraNumbers: List[int] = field(default_factory=list)
    positionNumbers: List[int] = field(default_factory=list)
    characterId: str = None
    motionType: str = None
    name: str = None
    lookTargetType: str = None
    disableLookTargetIdol: bool = None
    motionAssetIds: List[str] = field(default_factory=list)
    facialAssetIds: List[str] = field(default_factory=list)
    propAssetIds: List[Any] = field(default_factory=list)
    photoReactionVoiceGroupId: str = None
    photoWaitVoiceGroupId: str = None
    photoFacialMotionGroupId: str = None
    viewConditionSetId: str = None
    unlockConditionSetId: str = None
    order: int = None
    localization: PhotoPoseLocalization = None

@dataclass(slots=True)
class PhotoPoseLocalization:
    id: str = None
    name: str = None
