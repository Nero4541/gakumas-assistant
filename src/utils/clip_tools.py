import os
import pickle
import numpy as np

from dataclasses import dataclass
from typing import Optional, List

from src.core.ONNX import CLIPModelFromONNX
from src.utils.logger import logger

@dataclass
class CLIPMemoryItem:
    payload: any
    features: any

@dataclass
class CLIPRetrieveData:
    payload: any
    similarity: float

class CLIPTools:
    _memory_file_path: str
    _memory: List[CLIPMemoryItem]
    _engine: CLIPModelFromONNX

    def _load(self):
        """加载记忆"""
        if os.path.exists(self._memory_file_path):
            with open(self._memory_file_path, 'rb') as f:
                self._memory = pickle.load(f)
        else:
            self._memory = []

    def _save(self):
        """保存记忆到本地"""
        with open(self._memory_file_path, 'wb') as f:
            pickle.dump(self._memory, f)

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray):
        """计算余弦相似度"""
        a = a.flatten()
        b = b.flatten()
        return (np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))).item()

    def __init__(self, model_session: CLIPModelFromONNX, save_file_name: str):
        self._engine = model_session
        self._memory_file_path = os.path.join(os.getcwd(), "model/CLIP", save_file_name+".pkl")
        os.makedirs(os.path.dirname(self._memory_file_path), exist_ok=True)
        logger.info(f"Loading CLIP model from {self._memory_file_path}")
        self._load()

    def add_to_memory(self, image: np.array, payload, similarity_threshold: float = 0.9) -> bool:
        """
        添加图像到记忆中
        :param image: 图像
        :param payload: 载荷
        :param similarity_threshold:
        :return:
        """

        image_features = self._engine.forward(image)

        if image_features is None:
            raise RuntimeError("Image features is None")

        # 检查图像是否已经在记忆库中
        for data in self._memory:
            # 计算当前图像与已存图像特征的余弦相似度
            similarity = self._cosine_similarity(image_features, data.features)

            # 如果相似度超过阈值，认为是重复图像
            if similarity > similarity_threshold:
                logger.debug(f"Image already exists with similarity: {similarity:.4f}")
                return False

        # 如果图像未找到重复，添加到记忆库
        self._memory.append(CLIPMemoryItem(payload, image_features))
        logger.debug(f"Added image to memory")
        # 保存到本地文件
        self._save()
        return True

    def retrieve(self, image: np.array, similarity_threshold: float = 0.9) -> Optional[CLIPRetrieveData]:
        """
        使用图像检索记忆
        :param image: 图像
        :param similarity_threshold: 阈值
        :return: CLIPRetrieveData | None
        """

        image_features = self._engine.forward(image)

        if image_features is None:
            raise RuntimeError("Image features is None")

        # 计算图像与记忆库中所有图像特征的相似度
        similarities = []
        for data in self._memory:
            similarity = self._cosine_similarity(image_features, data.features)
            similarities.append(float(similarity))

        # 按相似度排序并返回最匹配的载荷
        if similarities:
            best_match_idx = np.argmax(similarities)
            best_match_similarity = similarities[best_match_idx]

            if best_match_similarity > similarity_threshold:
                matched_payload = self._memory[best_match_idx].payload
                return CLIPRetrieveData(matched_payload, best_match_similarity)

        return None