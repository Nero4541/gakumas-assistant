import os
from dataclasses import dataclass
from typing import List, Optional, Any

import cv2
import numpy as np

from src.entity.Game.Database.ProduceCard import ProduceCard
from src.models.clip import CLIPayload_SkillCard
from src.utils.game_database_tools import GakumasDatabase_ProduceCardDataUtils
from src.utils.logger import logger
from src.utils.clip_tools import CLIPTools, CLIPRetrieveData

produce_card_db = GakumasDatabase_ProduceCardDataUtils()

@dataclass
class SkillCardInfo:
    name: str
    type: str
    info: List[str]

class SkillCardCLIP(CLIPTools):
    def __init__(self, session):
        super().__init__(session, "skill_card")

    def _load_payload(self, payload_ref: "CLIPayload_SkillCard") -> Optional[ProduceCard]:
        return produce_card_db.get_by_id(payload_ref.id)

    def _save_payload(self, image: np.ndarray, features: np.ndarray, payload: Any):
        image_save_path = os.path.join(self._image_file_path, f"{payload.id}.png")
        if not os.path.exists(image_save_path):
            cv2.imwrite(image_save_path, image)
        obj, created = CLIPayload_SkillCard.get_or_create(
            id=payload.id
        )
        return obj

    def add_to_memory(self, image: np.ndarray, payload: SkillCardInfo, similarity_threshold=0.98, save_image=False):
        return super().add_to_memory(image, payload, similarity_threshold, save_image)

    def retrieve(self, image: np.ndarray, similarity_threshold: float = 0.98) -> Optional[SkillCardInfo]:
        result = super().retrieve(image, similarity_threshold)
        if result is None:
            return None
        return result.payload
