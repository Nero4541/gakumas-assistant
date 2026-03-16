"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class PhotoBackground:
    id: str = None
    name: str = None
    bgmAssetId: str = None
    category: str = None
    maxCharacterCount: int = None
    enableLookTargetPositionNumbers: List[int] = field(default_factory=list)
    backgroundAssetId: str = None
    timeTypes: List[str] = field(default_factory=list)
    photoBackgroundPrefab: str = None
    sceneLayoutId: str = None
    costumePhotoGroup: str = None
    ngCostumePhotoGroupId: str = None
    viewConditionSetId: str = None
    unlockConditionSetId: str = None
    order: int = None
    localization: PhotoBackgroundLocalization = None

@dataclass
class PhotoBackgroundLocalization:
    id: str = None
    name: str = None
