from dataclasses import dataclass
from typing import List


@dataclass(slots=True)
class EffectGroupLocalization:
    id: str
    name: str


@dataclass(slots=True)
class EffectGroup:
    id: str
    name: str
    examEffectType: str
    produceEffectType: str
    examEffectTypes: List[str]
    produceEffectTypes: List[str]
    hiddenFilter: bool
    produceCardGrowEffectTypes: List[str]
    order: int
    localization: EffectGroupLocalization = None
