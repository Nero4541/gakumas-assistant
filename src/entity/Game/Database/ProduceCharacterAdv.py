"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class ProduceCharacterAdv:
    produceType: str = None
    type: str = None
    characterId: str = None
    title: str = None
    assetId: str = None
    localization: ProduceCharacterAdvLocalization = None

@dataclass
class ProduceCharacterAdvLocalization:
    assetId: str = None
    title: str = None
