from dataclasses import dataclass
from typing import List

from src.entity.Game.Database.EffectGroup import EffectGroup
from src.entity.Game.Database.General import ProduceDescriptionItem, ProduceDescriptionLocalizationItem


@dataclass
class ProduceItemSkill:
    produceTriggerId: str
    produceItemEffectId: str


@dataclass
class ProduceItemLocalization:
    id: str
    name: str
    produceDescriptions: List[ProduceDescriptionLocalizationItem]


@dataclass
class ProduceItem:
    id: str
    assetId: str
    rarity: str
    name: str
    planType: str
    fireLimit: int
    fireInterval: int
    produceTriggerId: str
    produceTriggerIds: List[str]
    produceItemEffectIds: List[str]
    skills: List[ProduceItemSkill]
    libraryHidden: bool
    produceDescriptions: List[ProduceDescriptionItem]
    originIdolCardId: str
    originSupportCardId: str
    isUpgraded: bool
    isExamEffect: bool
    isChallenge: bool
    isResearch: bool
    isHighScoreRush: bool
    viewStartTime: str
    isLimited: bool
    effectGroupIds: List[str]
    evaluation: int
    order: str
    effectGroupClss: List[EffectGroup] = None
    localization: ProduceItemLocalization = None
