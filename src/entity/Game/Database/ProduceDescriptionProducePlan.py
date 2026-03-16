"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class ProduceDescriptionProducePlan:
    type: str = None
    name: str = None
    produceDescriptionLabelId: str = None
    planDetailProduceDescriptionLabelId: str = None
    localization: ProduceDescriptionProducePlanLocalization = None

@dataclass
class ProduceDescriptionProducePlanLocalization:
    type: str = None
    name: str = None
