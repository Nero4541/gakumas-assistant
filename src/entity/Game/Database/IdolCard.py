from dataclasses import dataclass
from typing import List

from src.entity.Game.Database.Character import Character
from src.entity.Game.Database.ProduceCard import ProduceCard
from src.entity.Game.Database.ProduceItem import ProduceItem


@dataclass
class IdolCardLocalization:
    id: str
    name: str


@dataclass
class IdolCard:
    id: str
    characterId: str
    originalIdolCardSkinId: str
    assetId: str
    name: str
    rarity: str
    isLimited: bool
    anotherCostumeHeadId: str
    anotherCostumeId: str
    idolCardPotentialId: str
    idolCardPotentialProduceSkillId: str
    idolCardLevelLimitId: str
    idolCardLevelLimitProduceSkillId: str
    maxIdolCardLevelLimitRank: str
    additionalAnotherCostumeHeadIds: List[str]
    additionalAnotherCostumeIds: List[str]
    planType: str
    idolCardLevelLimitStatusUpId: str
    produceVocal: int
    produceDance: int
    produceVisual: int
    produceVocalGrowthRatePermil: int
    produceDanceGrowthRatePermil: int
    produceVisualGrowthRatePermil: int
    produceStamina: int
    produceStepAuditionDifficultyId: str
    examInitialDeckId: str
    produceCardId: str
    beforeProduceItemId: str
    afterProduceItemId: str
    examEffectType: str
    produceChallengeSlotId: str
    showExamEffectType: str
    potentialRankVoiceAssetId: str
    produceSelectVoiceAssetId: str
    produceScheduleFrontVoiceGroupId: str
    produceScheduleBackVoiceGroupId: str
    useProduceCardVoiceAssetId: str
    viewStartTime: str
    order: str
    produceStoryIds: List[str]
    achievementIds: List[str]
    characterCls: Character = None
    produceCardCls: ProduceCard = None
    beforeProduceItemCls: ProduceItem = None
    afterProduceItemCls: ProduceItem = None
    localization: IdolCardLocalization = None
