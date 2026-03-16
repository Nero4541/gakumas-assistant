"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class ExamOutGameMotion:
    characterId: str = None
    type: str = None
    motionType: str = None
    number: int = None
    facialAssetIds: List[Any] = field(default_factory=list)
    bodyAssetIds: List[str] = field(default_factory=list)
    voiceAssetId: str = None
    sceneLayoutId: str = None
    cameraId: str = None
