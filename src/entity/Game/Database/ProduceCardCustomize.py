from dataclasses import dataclass
from typing import List

from src.entity.Game.Database.ProduceCardGrowEffect import ProduceCardGrowEffect


@dataclass
class ProduceCardCustomizeLocalization:
    id: str
    customizeCount: int
    description: str


@dataclass
class ProduceCardCustomize:
    id: str
    customizeCount: int
    overwriteProduceCardGrowEffectType: str
    description: str
    produceCardGrowEffectIds: List[str]
    producePoint: int
    produceCardGrowEffectClss: List[ProduceCardGrowEffect] = None
    localization: ProduceCardCustomizeLocalization = None
