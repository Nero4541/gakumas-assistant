from dataclasses import dataclass
from typing import List

from src.entity.Game.Database.General import ProduceDescriptionItem, ProduceDescriptionLocalizationItem
from src.entity.Game.Database.ProduceCardGrowEffect import ProduceCardGrowEffect
from src.entity.Game.Database.ProduceExamTrigger import ProduceExamTrigger


@dataclass(slots=True)
class ProduceCardStatusEnchantLocalization:
    id: str
    produceDescriptions: List[ProduceDescriptionLocalizationItem]


@dataclass(slots=True)
class ProduceCardStatusEnchant:
    id: str
    produceExamTriggerId: str
    produceCardGrowEffectIds: List[str]
    triggerCount: int
    produceDescriptions: List[ProduceDescriptionItem]
    effectGroupIds: List[str]
    produceExamTriggerCls: ProduceExamTrigger = None
    produceCardGrowEffectClss: List[ProduceCardGrowEffect] = None
    localization: ProduceCardStatusEnchantLocalization = None
