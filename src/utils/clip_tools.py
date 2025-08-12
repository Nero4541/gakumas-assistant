import os
import pickle
from uuid import UUID, uuid4

import cv2
import numpy as np

from dataclasses import dataclass
from typing import Optional, List

from src.core.ONNX import CLIPModelFromONNX
from src.models.clip import CLIPMemory, CLIPPayload
from src.utils.logger import logger

@dataclass
class CLIPRetrieveData:
    payload: any
    similarity: float

class CLIPTools:
    _image_file_path: str
    _type: str
    _engine: CLIPModelFromONNX

    def __init__(self, model_session: CLIPModelFromONNX, save_file_name: str):
        self._engine = model_session
        self._type = save_file_name
        self._image_file_path = os.path.join(os.getcwd(), "data/CLIP", save_file_name)
        os.makedirs(self._image_file_path, exist_ok=True)

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray):
        a = a.flatten()
        b = b.flatten()
        return (np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))).item()

    def add_to_memory(self, image: np.ndarray, payload, similarity_threshold: float = 0.9, save_image: bool = False) -> bool:
        image_features = self._engine.forward(image)
        if image_features is None:
            raise RuntimeError("Image features is None")

        # 查询同类型向量并比对相似度
        for memory in CLIPMemory.select().where(CLIPMemory.type == self._type):
            existing_features = pickle.loads(memory.features)
            similarity = self._cosine_similarity(image_features, existing_features)
            if similarity > similarity_threshold:
                logger.debug(f"Image already exists with similarity: {similarity:.4f}")
                return False

        # 存储 CLIPPayload（可复用）
        payload_hash = hash(pickle.dumps(payload))
        payload_record = CLIPPayload.save_payload(payload)

        # 保存 CLIPMemory
        CLIPMemory.create(
            type=self._type,
            payload=payload_record,
            features=pickle.dumps(image_features)
        )

        if save_image and not os.path.exists(save_name := f"{payload_hash}.png"):
            cv2.imwrite(os.path.join(self._image_file_path, save_name), image)

        logger.debug(f"[{payload_hash}] Added image to memory")
        return True

    def retrieve(self, image: np.ndarray, similarity_threshold: float = 0.9) -> Optional[CLIPRetrieveData]:
        image_features = self._engine.forward(image)
        if image_features is None:
            raise RuntimeError("Image features is None")

        best_similarity = -1
        best_payload = None

        for memory in CLIPMemory.select().where(CLIPMemory.type == self._type):
            existing_features = pickle.loads(memory.features)
            similarity = self._cosine_similarity(image_features, existing_features)

            if similarity > best_similarity:
                best_similarity = similarity
                best_payload = memory.payload

        if best_similarity > similarity_threshold:
            return CLIPRetrieveData(best_payload.load_payload(), best_similarity)

        return None