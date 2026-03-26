from dataclasses import dataclass
from typing import List

from src.entity.Game.Database.General import ProduceDescriptionItem, ProduceDescriptionLocalizationItem


@dataclass(slots=True)
class ProduceSkillLocalization:
    id: str
    level: int
    produceDescriptions: List[ProduceDescriptionLocalizationItem]


@dataclass(slots=True)
class ProduceSkill:
    id: str
    level: int
    rarity: str
    tag: str
    planType: str
    activationCount: int
    produceEffectId1: str
    produceTriggerId1: str
    activationRatePermil1: int
    produceEffectId2: str
    produceTriggerId2: str
    activationRatePermil2: int
    produceEffectId3: str
    produceTriggerId3: str
    activationRatePermil3: int
    produceDescriptions: List[ProduceDescriptionItem]
    localization: ProduceSkillLocalization = None
