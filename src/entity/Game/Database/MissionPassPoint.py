"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class MissionPassPoint:
    id: str = None
    name: str = None
    assetId: str = None
    localization: MissionPassPointLocalization = None

@dataclass
class MissionPassPointLocalization:
    id: str = None
    name: str = None
