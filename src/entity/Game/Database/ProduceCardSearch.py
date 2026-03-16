from dataclasses import dataclass
from typing import List

from src.entity.Game.Database.EffectGroup import EffectGroup
from src.entity.Game.Database.General import ProduceDescriptionItem, ProduceDescriptionLocalizationItem


@dataclass
class ProduceCardSearchLocalization:
    id: str
    produceDescriptions: List[ProduceDescriptionLocalizationItem]


@dataclass
class ProduceCardSearch:
    id: str
    cardRarities: List[str]
    produceCardIds: List[str]
    upgradeCounts: List[int]
    planType: str
    cardCategories: List[str]
    cardStatusType: str
    orderType: str
    cardPositionType: str
    cardSearchTag: str
    produceCardRandomPoolId: str
    limitCount: int
    staminaMinMaxType: str
    staminaMin: int
    staminaMax: int
    examEffectType: str
    effectGroupIds: List[str]
    isSelf: bool
    produceDescriptions: List[ProduceDescriptionItem]
    produceCardPoolId: str
    costType: str
    isCustomized: bool
    effectGroupClss: List[EffectGroup] = None
    localization: ProduceCardSearchLocalization = None
