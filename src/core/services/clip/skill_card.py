from dataclasses import dataclass
from typing import List, Optional, Any

import numpy as np

from src.utils.logger import logger
from src.utils.clip_tools import CLIPTools, CLIPRetrieveData


@dataclass
class SkillCardInfo:
    name: str
    type: str
    info: List[str]

class SkillCardCLIP(CLIPTools):
    def __init__(self, session):
        super().__init__(session, "skill_card")

    def _load_payload(self, payload_ref):
        pass

    def _save_payload(self, image: np.ndarray, features: np.ndarray, payload: Any):
        pass

    def add_to_memory(self, image: np.ndarray, payload: SkillCardInfo, similarity_threshold=0.9, save_image=False):
        return super().add_to_memory(image, payload, similarity_threshold, save_image)

    def retrieve(self, image: np.ndarray, similarity_threshold: float = 0.9) -> Optional[SkillCardInfo]:
        result = super().retrieve(image, similarity_threshold)
        if result is None:
            return None
        return result.payload
