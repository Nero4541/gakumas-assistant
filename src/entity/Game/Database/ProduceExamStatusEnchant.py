from dataclasses import dataclass
from typing import List

from src.entity.Game.Database.General import ProduceDescriptionItem, ProduceDescriptionLocalizationItem
from src.entity.Game.Database.ProduceExamEffect import ProduceExamEffect
from src.entity.Game.Database.ProduceExamTrigger import ProduceExamTrigger


@dataclass
class ProduceExamStatusEnchantLocalization:
    id: str
    produceDescriptions: List[ProduceDescriptionLocalizationItem]


@dataclass
class ProduceExamStatusEnchant:
    id: str
    assetId: str
    produceDescriptions: List[ProduceDescriptionItem]
    produceExamTriggerId: str
    produceExamEffectIds: List[str]
    produceExamTriggerCls: ProduceExamTrigger = None
    produceExamEffectClss: List[ProduceExamEffect] = None
    localization: ProduceExamStatusEnchantLocalization = None
