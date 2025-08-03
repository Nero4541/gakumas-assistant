from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from src.utils.logger import logger
from src.utils.clip_tools import CLIPTools

@dataclass
class ItemInfo:
    name: str
    info: List[str]


class ItemCLIP(CLIPTools):
    def __init__(self,session):
        super().__init__(session, "items")

    def add_to_memory(self, image: np.array, payload: ItemInfo, similarity_threshold=0.98):
        logger.debug(f"[ItemCLIP]Add Item: {payload}")
        return super().add_to_memory(image, payload, similarity_threshold)

    def retrieve(self, image: np.array, similarity_threshold: float = 0.98) -> Optional[ItemInfo]:
        result = super().retrieve(image, similarity_threshold)
        logger.debug(f"[ItemCLIP]Retrieve Result: {result}")
        if result is None:
            return None
        return result.payload