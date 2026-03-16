"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class CharacterPushMessage:
    characterId: str = None
    type: str = None
    number: int = None
    title: str = None
    message: str = None
    localization: CharacterPushMessageLocalization = None

@dataclass
class CharacterPushMessageLocalization:
    characterId: str = None
    type: str = None
    number: int = None
    title: str = None
    message: str = None
