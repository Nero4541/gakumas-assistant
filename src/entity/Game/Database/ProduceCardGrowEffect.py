from dataclasses import dataclass
from typing import List

from src.entity.Game.Database.ProduceExamEffect import ProduceExamEffect
from src.entity.Game.Database.ProduceExamTrigger import ProduceExamTrigger


@dataclass(slots=True)
class ProduceCardGrowEffect:
    """成长效果"""
    # 效果id
    id: str
    # 效果类型
    effectType: str
    #
    costType: str
    value: str
    playProduceExamTriggerId: str
    playEffectProduceExamTriggerId: str
    targetPlayEffectProduceExamTriggerIds: List[str]
    playProduceExamEffectId: str
    targetPlayProduceExamEffectIds: List[str]
    produceCardStatusEnchantId: str
    playMovePositionType: str
    effectGroupIds: List[str]
    playProduceExamTriggerCls: ProduceExamTrigger = None
    playEffectProduceExamTriggerCls: ProduceExamTrigger = None
    targetPlayEffectProduceExamTriggerClss: List[ProduceExamTrigger] = None
    playProduceExamEffectCls: ProduceExamEffect = None
    targetPlayProduceExamEffectClss: List[ProduceExamEffect] = None
