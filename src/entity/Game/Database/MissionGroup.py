"""
Auto-generated from assets/gakumasu-diff and localization JSON.
Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class MissionGroupRewardsItem:
    resourceType: str = None
    resourceId: str = None
    quantity: int = None

@dataclass
class MissionGroup:
    id: str = None
    name: str = None
    assetId: str = None
    missionPointId: str = None
    missionIds: List[str] = field(default_factory=list)
    rewards: List[MissionGroupRewardsItem] = field(default_factory=list)
    showHomeLimitedMission: bool = None
    rewardName: str = None
    rewardAssetId: str = None
    conditionSetId: str = None
    order: int = None
    localization: MissionGroupLocalization = None

@dataclass
class MissionGroupLocalization:
    id: str = None
    name: str = None
