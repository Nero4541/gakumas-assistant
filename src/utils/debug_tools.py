import os.path
from dataclasses import dataclass, field
from threading import Lock
from time import time
from typing import Tuple, List, Optional

import cv2
import numpy as np

from src.entity.Base import SingletonMeta
from src.utils.opencv_tools import draw_text


@dataclass
class DebugBox:
    x: int
    y: int
    w: int
    h: int
    color: Tuple[int, int, int] = (0, 0, 255)
    alpha: float = 0.4
    duration: float = 60.0
    label: Optional[str] = None
    text_color: Tuple[int, int, int] = (255, 255, 255)
    font_size: int = 22
    thickness: int = 2
    created_at: float = field(default_factory=time)

    def __post_init__(self):
        for name, value in [("x", self.x), ("y", self.y), ("w", self.w), ("h", self.h)]:
            if not isinstance(value, int):
                raise TypeError(f"{name} must be int, got {type(value).__name__}")
        if self.x >= self.w:
            raise ValueError(f"Invalid box coordinates: x({self.x}) >= w({self.w})")
        if self.y >= self.h:
            raise ValueError(f"Invalid box coordinates: y({self.y}) >= h({self.h})")

    @property
    def expire_time(self) -> float:
        return self.created_at + self.duration

    @property
    def top_left(self) -> Tuple[int, int]:
        return self.x, self.y

    @property
    def bottom_right(self) -> Tuple[int, int]:
        return self.w, self.h

class DebugTools(metaclass=SingletonMeta):
    _boxes: List[DebugBox] = []
    _lock: Lock = Lock()
    _hide: bool = False

    def add_box(
            self,
            *args,
            **kwargs,
    ):
        """
        绘制一个调试框
        """
        with self._lock:
            self._boxes.append(DebugBox(
                *args, **kwargs,
            ))

    def _clear_expired(self):
        """清除过期框"""
        now = time()
        with self._lock:
            self._boxes = [box for box in self._boxes if box.expire_time > now]

    def clear_all_boxes(self):
        """
        清除所有调试框
        :return:
        """
        with self._lock:
            self._boxes = []

    def hide(self):
        with self._lock:
            self._hide = True

    def show(self):
        with self._lock:
            self._hide = False

    def draw_boxes(self, image: np.ndarray) -> np.ndarray:
        """在图像上绘制所有当前调试框及其文字标签"""
        self._clear_expired()
        if self._hide:
            return image
        with self._lock:
            for box in self._boxes:
                # 半透明矩形框
                overlay = image.copy()
                cv2.rectangle(overlay, box.top_left, box.bottom_right, box.color, -1)
                image = cv2.addWeighted(overlay, box.alpha, image, 1 - box.alpha, 0)
                if box.label:
                    x, y = box.top_left
                    image = draw_text(
                        image,
                        box.label,
                        (x,y),
                        os.path.join(os.getcwd(), "assets/NotoSerifCJKsc-Medium.otf"),
                        box.font_size,
                        box.text_color,
                        box.w - box.x,
                        line_spacing=box.thickness
                    )
        return image
