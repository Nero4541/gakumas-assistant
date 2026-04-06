from dataclasses import dataclass, field
from typing import List

from src.entity.Game.Database.General import ProduceDescriptionItem, GeneralProduceDescriptionsLocalization


@dataclass(slots=True)
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
    targetProduceCardId: str = ""
    # 目标卡牌所需强化等级（未指定目标卡时无效）
    targetUpgradeCount: int = 0
    # 要修改的目标效果类型（未知 = 未使用）
    targetExamEffectType: str = ""
    # 用于筛选受影响卡牌的搜索规则ID
    produceCardSearchId: str = ""
    # 应用效果后卡牌移动的位置
    movePositionType: str = ""
    pickRangeType: str = ""
    pickCountType: str = ""
    pickCountReferenceProduceCardSearchId: str = ""
    pickCountMin: int = 0
    pickCountMax: int = 0
    chainProduceExamEffectId: str = ""
    produceExamStatusEnchantId: str = ""
    produceCardStatusEnchantId: str = ""
    produceCardGrowEffectIds: List[str] = field(default_factory=list)
    effectGroupIds: List[str] = field(default_factory=list)
    # 效果介绍
    produceDescriptions: List[ProduceDescriptionItem] = field(default_factory=list)
    customizeProduceDescriptions: List[ProduceDescriptionItem] = field(default_factory=list)
    localization: GeneralProduceDescriptionsLocalization = None
