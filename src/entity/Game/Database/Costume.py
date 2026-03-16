"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class Costume:
    id: str = None
    characterId: str = None
    name: str = None
    motifId: str = None
    description: str = None
    costumeColorGroupId: str = None
    costumeHeadId: str = None
    defaultCostumeHeadId: str = None
    voiceGroupId: str = None
    resourceOriginType: str = None
    targetId: str = None
    isTraining: bool = None
    isBarefoot: bool = None
    isCommonThumbnail: bool = None
    invalidCostumeFeatureTypes: List[str] = field(default_factory=list)
    costumeWaitMotionNumber: int = None
    viewConditionSetId: str = None
    viewStartTime: str = None
    order: int = None
    localization: CostumeLocalization = None

@dataclass
class CostumeLocalization:
    id: str = None
    name: str = None
    description: str = None
