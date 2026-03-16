"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class ProduceStepSelfLessonMotion:
    characterId: str = None
    stepType: str = None
    number: int = None
    motionAssetId: str = None
    voiceAssetId: str = None
    bgmAssetId: str = None
    sceneLayoutId: str = None
    cameraId: str = None
    propAssetIds: List[str] = field(default_factory=list)
    disableLipSync: bool = None
