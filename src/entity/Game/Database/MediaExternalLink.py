"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass(slots=True)
class MediaExternalLink:
    id: str = None
    url: str = None
    assetId: str = None
    ignorePlatformTypes: List[Any] = field(default_factory=list)
    viewConditionSetId: str = None
    order: int = None
