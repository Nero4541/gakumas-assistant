import abc
import os
import pickle
from abc import abstractmethod

import numpy as np

from dataclasses import dataclass
from typing import Optional, Any

from src.core.inference.ONNX import CLIPModelFromONNX
from src.models.clip import CLIPMemory
from src.utils.logger import logger

@dataclass
class CLIPRetrieveData:
    payload: Any
    similarity: float

class CLIPTools(abc.ABC):
    _image_file_path: str
    _clip_name: str
    _engine: CLIPModelFromONNX

    def __init__(self, model_session: CLIPModelFromONNX, clip_name: str):
        self._engine = model_session
        self._clip_name = clip_name
        self._image_file_path = os.path.join(os.getcwd(), "data/CLIP", clip_name)
        os.makedirs(self._image_file_path, exist_ok=True)

    @ staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray):
        """计算向量相似度"""
        a = a.flatten()
        b = b.flatten()
        return (np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))).item()

    @abstractmethod
    def _save_payload(self, image: np.ndarray, features: np.ndarray, payload: Any):
        pass

    @abstractmethod
    def _load_payload(self, payload_ref):
        pass

    def add_to_memory(self, image: np.ndarray, payload, similarity_threshold: float = 0.9, save_image: bool = False) -> bool:
        image_features = self._engine.forward(image)
        if image_features is None:
            raise RuntimeError("Image features is None")

        # 查询同类型向量并比对相似度
        for memory in CLIPMemory.select().where(CLIPMemory.clip_name == self._clip_name):
            existing_features = pickle.loads(memory.features)
            similarity = self._cosine_similarity(image_features, existing_features)
            if similarity > similarity_threshold:
                logger.debug(f"Image already exists with similarity: {similarity:.4f}")
                return False

        payload_ref = self._save_payload(image, image_features, payload)

        CLIPMemory.save_vector(
            clip_name=self._clip_name,
            payload_obj=payload_ref,
            features=pickle.dumps(image_features)
        )
        return True

    def retrieve(self, image: np.ndarray, similarity_threshold: float = 0.9) -> Optional[CLIPRetrieveData]:
        image_features = self._engine.forward(image)
        if image_features is None:
            raise RuntimeError("Image features is None")

        best_similarity = -1
        best_payload = None

        for memory in CLIPMemory.select().where(CLIPMemory.clip_name == self._clip_name):
            existing_features = pickle.loads(memory.features)
            similarity = self._cosine_similarity(image_features, existing_features)

            if similarity > best_similarity:
                best_similarity = similarity
                best_payload = memory.load_payload()

        if best_similarity > similarity_threshold:
            return CLIPRetrieveData(self._load_payload(best_payload), best_similarity)

        return None