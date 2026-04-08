import abc
import os
import pickle
from abc import abstractmethod

import cv2
import numpy as np

from dataclasses import dataclass
from typing import Optional, Any, List

from src.core.inference.ONNX import CLIPModelFromONNX
from src.models.clip import CLIPMemory
from src.utils.logger import logger
from src.utils.runtime_paths import resolve_data_str

@dataclass
class CLIPRetrieveData:
    payload: Any
    similarity: float


def _augment_image(image: np.ndarray) -> List[np.ndarray]:
    """生成多种数据增强版本，提升 CLIP 检索对噪点/色偏/压缩的鲁棒性。

    Returns:
        增强后的图像列表（不含原图）。
    """
    augmented = []
    h, w = image.shape[:2]

    # 1. JPEG 压缩伪影（Q30 ~ 中低质量）
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 30]
    _, buf = cv2.imencode(".jpg", image, encode_param)
    augmented.append(cv2.imdecode(buf, cv2.IMREAD_COLOR))

    # 2. 高斯噪点 (σ=15)
    noise = np.random.normal(0, 15, image.shape).astype(np.float32)
    noisy = np.clip(image.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    augmented.append(noisy)

    # 3. 亮度/对比度偏移（亮度+20, 对比度×1.15）
    bright = cv2.convertScaleAbs(image, alpha=1.15, beta=20)
    augmented.append(bright)

    # 4. 色调偏移（HSV H通道±8）
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.int16)
    hsv[:, :, 0] = (hsv[:, :, 0] + 8) % 180
    augmented.append(cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR))

    # 5. 轻微缩放（0.85x 后 resize 回原尺寸，模拟分辨率差异）
    small = cv2.resize(image, (int(w * 0.85), int(h * 0.85)), interpolation=cv2.INTER_AREA)
    augmented.append(cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR))

    return augmented


class CLIPTools(abc.ABC):
    _image_file_path: str
    _clip_name: str
    _engine: CLIPModelFromONNX

    def __init__(self, model_session: CLIPModelFromONNX, clip_name: str):
        self._engine = model_session
        self._clip_name = clip_name
        self._image_file_path = resolve_data_str("CLIP", clip_name)
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

    def add_to_memory(self, image: np.ndarray, payload, similarity_threshold: float = 0.9,
                      save_image: bool = False, augment: bool = True) -> bool:
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

        # 存储原始特征
        CLIPMemory.save_vector(
            clip_name=self._clip_name,
            payload_obj=payload_ref,
            features=pickle.dumps(image_features)
        )

        # 存储增强版本的特征向量，提升对噪点/色偏/压缩的鲁棒性
        if augment:
            aug_count = 0
            for aug_image in _augment_image(image):
                aug_features = self._engine.forward(aug_image)
                if aug_features is None:
                    continue
                # 只存储与原始特征差异足够大的增强版本
                aug_sim = self._cosine_similarity(image_features, aug_features)
                if aug_sim < similarity_threshold:
                    CLIPMemory.save_vector(
                        clip_name=self._clip_name,
                        payload_obj=payload_ref,
                        features=pickle.dumps(aug_features)
                    )
                    aug_count += 1
            if aug_count > 0:
                logger.debug(f"Stored {aug_count} augmented feature vectors")

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
                # CLIP 记忆库可能残留已失效的 payload 引用。
                # 这类脏数据不应直接中断主流程，而应跳过后继续寻找下一条候选。
                try:
                    payload_ref = memory.load_payload()
                except Exception as exc:  # noqa: BLE001 - 这里需要兜底脏库数据
                    logger.warning(
                        f"CLIP '{self._clip_name}' 跳过失效记忆条目 {getattr(memory, 'id', '?')}: {exc}"
                    )
                    continue
                if payload_ref is None:
                    logger.debug(
                        f"CLIP '{self._clip_name}' 记忆条目 {getattr(memory, 'id', '?')} 未加载到 payload，跳过"
                    )
                    continue
                best_similarity = similarity
                best_payload = payload_ref

        if best_payload is not None and best_similarity > similarity_threshold:
            return CLIPRetrieveData(self._load_payload(best_payload), best_similarity)

        return None
