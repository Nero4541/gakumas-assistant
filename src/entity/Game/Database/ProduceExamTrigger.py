from dataclasses import dataclass
from typing import List

from src.entity.Game.Database.General import ProduceDescriptionItem


@dataclass
class ProduceExamTrigger:
    """考试触发器"""
    # 触发器ID
    id: str
    # 可激活此触发器的考试阶段列表
    phaseTypes: List[str]
    # 需匹配的具体回合数或子阶段值（空 = 指定阶段内的任意回合）
    phaseValues: List[int]
    # 执行的场地状态比较类型（如“大于”）；空 = 默认精确匹配
    fieldStatusCheckTypes: List[str]
    # 被监控的场地状态类型
    fieldStatusTypes: List[str]
    # 场地状态所需值；此处“检索次数提升”状态必须恰好为7
    fieldStatusValues: List[int]
    # 受该状态影响的特定卡牌搜索规则
    fieldStatusProduceCardSearchIds: List[str]
    # 触发器自身的通用卡牌搜索规则
    produceCardSearchId: str
    # 可检索卡牌数量的上限
    upperSearchCount: int
    # 可检索卡牌数量的下限
    lowerSearchCount: int
    # 移动卡牌的目标位置
    cardMovePositionType: str
    # 必须存在的考试效果类型
    effectTypes: List[str]
    # 与此触发器相关的课程类型
    lessonType: str
    produceDescriptions: List[ProduceDescriptionItem]
    playProduceDescriptions: List[ProduceDescriptionItem]
    playEffectProduceDescriptions: List[ProduceDescriptionItem]
    localization: List[ProduceDescriptionItem] = None
