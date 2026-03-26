from dataclasses import dataclass
from typing import List

@dataclass(slots=True)
class ItemGashas:
    id: str
    bannerAssetId: str
    hasFixReward: bool
    viewConditionSetId: str
    unlockConditionSetId: str
    startTime: str
    endTime: str

@dataclass(slots=True)
class ItemLocalization:
    id: str
    name: str
    description: str
    acquisitionRouteDescription: str

@dataclass(slots=True)
class Item:
    id: str
    name: str
    description: str
    acquisitionRouteDescription: str
    assetId: str
    type: str
    rarity: str
    commonLimitTime: str
    personalLimitDay: int
    sellPrice: int
    effectValue: int
    viewWithoutPossession: bool
    exchangeType: str
    exchangeId: str
    gashaId: str
    coinGashaId: str
    shopCoinGashaId: str
    storyEventId: str
    produceHighScoreEventId: str
    researchEventId: str
    tourEventId: str
    idolCardRarity: str
    supportCardRarity: str
    characterId: str
    gashas: List[ItemGashas]
    viewConditionSetId: str
    unlockConditionSetId: str
    startTime: str
    endTime: str
    order: int
    localization: ItemLocalization = None
