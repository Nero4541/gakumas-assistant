"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class ProducerRankingTower:
    id: str = None
    towerId: str = None
    layerNumbers: List[int] = field(default_factory=list)
