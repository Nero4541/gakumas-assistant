from dataclasses import dataclass
from typing import List


@dataclass(slots=True)
class CharacterLocalization:
    id: str
    lastName: str
    firstName: str


@dataclass(slots=True)
class Character:
    id: str
    lastName: str
    firstName: str
    alphabetLastName: str
    alphabetFirstName: str
    isPlayable: bool
    personalityType: str
    characterTrueEndBonusId: str
    achievementIds: List[str]
    masterAchievementId: str
    idolCardIds: List[str]
    supportCardIds: List[str]
    changeCostumeConditionSetId: str
    viewConditionSetId: str
    normalCostumeHeadId: str
    trainingCostumeHeadId: str
    liveCostumeHeadId: str
    normalCostumeId: str
    trainingCostumeId: str
    liveCostumeId: str
    dearnessMissionGroupId: str
    dearnessStoryUnlockItemId: str
    otherStoryIds: List[str]
    potentialRank1VoiceAssetId: str
    potentialRank3VoiceAssetId: str
    potentialRank4VoiceAssetId: str
    standingListPositionX: int
    standingListPositionY: int
    rosterDetailPositionX: int
    rosterDetailPositionY: int
    storyPositionX: int
    storyPositionY: int
    produceHighScorePositionX: int
    produceHighScorePositionY: int
    produceHighScoreRushPositionX: int
    produceHighScoreRushPositionY: int
    order: int
    localization: CharacterLocalization = None
