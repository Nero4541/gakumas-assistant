"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class Shop:
    id: str = None
    type: str = None
    name: str = None
    resetTimingType: str = None
    resetHour: int = None
    resetMinute: int = None
    resetWeekday: str = None
    resetDay: int = None
    startTime: str = None
    endTime: str = None
    order: int = None
    localization: ShopLocalization = None

@dataclass
class ShopLocalization:
    id: str = None
    name: str = None
