from dataclasses import dataclass
from typing import List

from src.entity.Game.Database.General import ProduceDescriptionItem, GeneralProduceDescriptionsLocalization


@dataclass
class ProduceExamEffect:
    id: str
    # 效果类型
    effectType: str
    # 效果数值
    effectValue1: int
    effectValue2: int
    # 效果次数
    effectCount: int
    # 持续回合
    effectTurn: int
    # 目标卡牌ID（空 = 通用效果，非特定卡牌）
    targetProduceCardId: str
    # 目标卡牌所需强化等级（未指定目标卡时无效）
    targetUpgradeCount: int
    # 要修改的目标效果类型（未知 = 未使用）
    targetExamEffectType: str
    # 用于筛选受影响卡牌的搜索规则ID
    produceCardSearchId: str
    # 应用效果后卡牌移动的位置
    movePositionType: str
    pickRangeType: str
    pickCountType: str
    pickCountReferenceProduceCardSearchId: str
    pickCountMin: int
    pickCountMax: int
    chainProduceExamEffectId: str
    produceExamStatusEnchantId: str
    produceCardStatusEnchantId: str
    produceCardGrowEffectIds: List[str]
    effectGroupIds: List[str]
    # 效果介绍
    produceDescriptions: List[ProduceDescriptionItem]
    customizeProduceDescriptions: List[ProduceDescriptionItem]
    localization: GeneralProduceDescriptionsLocalization = None
