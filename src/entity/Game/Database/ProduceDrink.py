from dataclasses import dataclass
from typing import List

from src.entity.Game.Database.EffectGroup import EffectGroup
from src.entity.Game.Database.General import ProduceDescriptionItem, ProduceDescriptionLocalizationItem


@dataclass
class ProduceDrinkLocalization:
    id: str
    name: str
    produceDescriptions: List[ProduceDescriptionLocalizationItem]


@dataclass
class ProduceDrink:
    id: str
    assetId: str
    name: str
    planType: str
    produceDrinkEffectIds: List[str]
    rarity: str
    produceDescriptions: List[ProduceDescriptionItem]
    unlockProducerLevel: int
    viewStartTime: str
    libraryHidden: bool
    originSupportCardId: str
    effectGroupIds: List[str]
    order: str
    effectGroupClss: List[EffectGroup] = None
    localization: ProduceDrinkLocalization = None
