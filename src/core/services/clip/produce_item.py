import os
from typing import Optional

import cv2
import numpy as np

from src.entity.Game.Database.ProduceItem import ProduceItem
from src.models.clip import CLIPayload_ProduceItem, CLIPMemory
from src.utils.clip_tools import CLIPTools
from src.utils.game_database_tools import GakumasDatabase_ProduceItemDataUtils

produce_item_db = GakumasDatabase_ProduceItemDataUtils()


class ProduceItemCLIP(CLIPTools):
    """P物品专用 CLIP 服务。"""

    def __init__(self, session):
        super().__init__(session, "produce_item")

    def _save_payload(self, image: np.ndarray, features: np.ndarray, payload: ProduceItem):
        image_save_path = os.path.join(self._image_file_path, f"{payload.id}.png")
        if not os.path.exists(image_save_path):
            cv2.imwrite(image_save_path, image)
        obj, _created = CLIPayload_ProduceItem.get_or_create(id=payload.id)
        return obj

    def _load_payload(self, payload_ref: "CLIPayload_ProduceItem") -> Optional[ProduceItem]:
        return produce_item_db.get_by_id(payload_ref.id)

    def add_to_memory(
        self,
        image: np.ndarray,
        payload: ProduceItem,
        similarity_threshold: float = 0.98,
        save_image: bool = False,
    ):
        payload_ref = CLIPayload_ProduceItem.get_or_none(CLIPayload_ProduceItem.id == payload.id)
        if payload_ref is not None and CLIPMemory.select().where(
            CLIPMemory._payload_id == str(payload_ref.get_id())
        ).exists():
            return False
        return super().add_to_memory(image, payload, similarity_threshold, save_image)

    def retrieve(self, image: np.ndarray, similarity_threshold: float = 0.96) -> Optional[ProduceItem]:
        result = super().retrieve(image, similarity_threshold)
        if result is None:
            return None
        return result.payload
