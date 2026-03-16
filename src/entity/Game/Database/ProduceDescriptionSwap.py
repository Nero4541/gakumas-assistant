"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class ProduceDescriptionSwap:
    id: str = None
    swapType: str = None
    text: str = None
    localization: ProduceDescriptionSwapLocalization = None

@dataclass
class ProduceDescriptionSwapLocalization:
    id: str = None
    swapType: str = None
    text: str = None
