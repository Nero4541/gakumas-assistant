"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class MissionPoint:
    id: str = None
    name: str = None
    resetTimingType: str = None
    assetId: str = None
    localization: MissionPointLocalization = None

@dataclass
class MissionPointLocalization:
    id: str = None
    name: str = None
