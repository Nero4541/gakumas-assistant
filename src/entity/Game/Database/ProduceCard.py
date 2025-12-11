from dataclasses import dataclass
from typing import List

from src.entity.Game.Database.General import ProduceDescriptionLocalizationItem, ProduceDescriptionItem
from src.entity.Game.Database.ProduceExamEffect import ProduceExamEffect
from src.entity.Game.Database.ProduceExamTrigger import ProduceExamTrigger


@dataclass
class ProduceCardPlayEffects:
    produceExamTriggerId: str
    produceExamEffectId: str
    produceExamTriggerCls: ProduceExamTrigger = None
    produceExamEffectCls: ProduceExamEffect = None
    hideIcon: bool = False

@dataclass
class ProduceCardLocalization:
    id: str
    name: str
    upgradeCount: int
    produceDescriptions: List[ProduceDescriptionLocalizationItem]

@dataclass
class ProduceCard:
    """技能卡"""
    id: str
    # 等级
    upgradeCount: int
    # 显示名称
    name: str
    # 资源id
    assetId: str
    # 是否为角色专属卡
    isCharacterAsset: bool
    # 稀有度
    rarity: str
    # 培养计划类型（在什么培养计划中可出现）
    planType: str
    # 卡牌所属类别
    category: str
    # 消耗体力
    stamina: int
    # 强制消耗体力（红心）
    forceStamina: int
    # 卡牌使用成本（好印象 元气之类的）
    costType: str
    # 使用成本值
    costValue: int
    # 此卡使用时激活的触发器ID
    playProduceExamTriggerId: str
    playEffects: List[ProduceCardPlayEffects]
    playMovePositionType: str
    moveEffectTriggerType: str
    moveProduceExamEffectIds: list[str]
    isEndTurnLost: bool
    isInitial: bool
    isRestrict: bool
    produceCardStatusEnchantId: str
    searchTag: str
    libraryHidden: bool
    noDeckDuplication: bool
    isReward: bool
    unlockProducerLevel: int
    rentalUnlockProducerLevel: int
    evaluation: int
    originIdolCardId: str
    originSupportCardId: str
    isInitialDeckProduceCard: bool
    effectGroupIds: List[str]
    produceCardCustomizeIds: List[str]
    maxCustomizeCount: int
    viewStartTime: str
    isLimited: bool
    order: str
    produceDescriptions: List[ProduceDescriptionItem]
    playProduceExamTriggerCls: ProduceExamTrigger = None
    localization: ProduceCardLocalization = None
