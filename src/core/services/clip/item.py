import os.path
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from src.constants.path.data_path import DataPath
from src.models.clip import CLIPayload_Item
from src.utils.diff_tools import GakumasuDiffItemDataUtils
from src.utils.logger import logger
from src.utils.clip_tools import CLIPTools

item_db = GakumasuDiffItemDataUtils(DataPath.GakumasuDiffData.ITEM)

@dataclass
class Item:
    id: str
    name: str
    description: str

class ItemCLIP(CLIPTools):
    def __init__(self,session):
        super().__init__(session, "items")

    def _save_payload(self, image, features, payload: "Item"):
        image_save_path = os.path.join(self._image_file_path, f"{payload.id}.png")
        if not os.path.exists(image_save_path):
            cv2.imwrite(image_save_path, image)
        obj, created = CLIPayload_Item.get_or_create(
            item_id=payload.id
        )
        return obj

    def _load_payload(self, payload_ref: "CLIPayload_Item"):
        item_id = payload_ref.item_id
        result = item_db.get_by_id(item_id)
        return Item(id = result.id, name = result.name, description = result.description)

    def add_to_memory(self, image: np.ndarray, payload: Item, similarity_threshold=0.98, save_image=False):
        logger.debug(f"[ItemCLIP]Add Item: {payload}")
        return super().add_to_memory(image, payload, similarity_threshold, save_image)

    def retrieve(self, image: np.ndarray, similarity_threshold: float = 0.98) -> Optional[Item]:
        result = super().retrieve(image, similarity_threshold)
        logger.debug(f"[ItemCLIP]Retrieve Result: {result}")
        if result is None:
            return None
        return result.payload