from dataclasses import dataclass
from typing import List


@dataclass
class ProduceDescriptionItem:
    """介绍"""
    # 介绍类型 -> ProduceDescriptionType
    produceDescriptionType: str
    # 考试介绍类型
    examDescriptionType: str
    # 考试效果类型
    examEffectType: str
    # 成长效果类型
    produceCardGrowEffectType: str
    # 卡片分组
    produceCardCategory: str
    # 卡片移动类型
    produceCardMovePositionType: str
    produceStepType: str
    # 文本
    text: str
    targetId: str
    targetLevel: int
    effectValue1: int
    effectValue2: int
    effectCount: int
    turn: int
    costValue: int
    produceDescriptionSwapId: str
    originProduceExamTriggerId: str
    originProduceExamEffectId: str
    originProduceCardStatusEnchantId: str
    isCost: bool
    isOnlyOutGame: bool
    changeColor: bool

@dataclass
class ProduceDescriptionLocalizationItem:
    produceDescriptionType: str
    examDescriptionType: str
    examEffectType: str
    produceCardCategory: str
    produceCardMovePositionType: str
    produceStepType: str
    targetId: str
    text: str

@dataclass
class GeneralProduceDescriptionsLocalization:
    id: str
    produceDescriptions: List[ProduceDescriptionLocalizationItem]
