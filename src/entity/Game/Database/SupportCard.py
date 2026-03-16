from dataclasses import dataclass
from typing import List

from src.entity.Game.Database.General import ProduceDescriptionItem, ProduceDescriptionLocalizationItem
from src.entity.Game.Database.ProduceCardSearch import ProduceCardSearch


@dataclass
class SupportCardExchangeReward:
    resourceType: str
    resourceId: str
    quantity: int


@dataclass
class SupportCardLocalization:
    id: str
    name: str
    upgradeProduceCardProduceDescriptions: List[ProduceDescriptionLocalizationItem]


@dataclass
class SupportCard:
    id: str
    characterIds: List[str]
    name: str
    type: str
    planType: str
    rarity: str
    assetId: str
    supportCardLevelId: str
    supportCardLevelLimitId: str
    produceStoryIds: List[str]
    displayPositionX: int
    displayPositionY: int
    displayScale: int
    exchangeReward: SupportCardExchangeReward
    isLimited: bool
    produceCardUpgradePermil: int
    upgradeProduceCardSearchId: str
    produceCardUpgradeLessonParameterType: str
    gashaSupportAnimationNumber: int
    upgradeProduceCardProduceDescriptions: List[ProduceDescriptionItem]
    viewStartTime: str
    order: str
    upgradeProduceCardSearchCls: ProduceCardSearch = None
    localization: SupportCardLocalization = None
