from dataclasses import dataclass, field
from threading import Lock
from time import time
from typing import Tuple, List, Optional

import cv2
import numpy as np


@dataclass
class DebugBox:
    x: int
    y: int
    w: int
    h: int
    color: Tuple[int, int, int] = (0, 0, 255)
    alpha: float = 0.4
    duration: float = 10.0
    label: Optional[str] = None
    text_color: Tuple[int, int, int] = (255, 255, 255)
    font_scale: float = 0.5
    thickness: int = 1
    created_at: float = field(default_factory=time)

    @property
    def expire_time(self) -> float:
        return self.created_at + self.duration

    @property
    def top_left(self) -> Tuple[int, int]:
        return self.x, self.y

    @property
    def bottom_right(self) -> Tuple[int, int]:
        return self.w, self.h

class DebugTools:
    _boxes: List[DebugBox]
    _lock: Lock

    def __init__(self):
        self._boxes: List[DebugBox] = []
        self._lock = Lock()

    def add_box(
            self,
            x: int,
            y: int,
            w: int,
            h: int,
            color: Tuple[int, int, int] = (0, 0, 255),
            alpha: float = 0.4,
            duration: float = 10.0,
            label: Optional[str] = None,
            text_color: Tuple[int, int, int] = (255, 255, 255),
            font_scale: float = 0.5,
            thickness: int = 1,
    ):
        """
        绘制一个调试框
        :param x: x
        :param y: y
        :param w: w
        :param h: h
        :param color: 颜色
        :param alpha: 半透明
        :param duration: 消失时间
        :param label: 文本
        :param text_color: 文本颜色
        :param font_scale: 字体大小
        :param thickness: 字体粗细
        :return:
        """
        with self._lock:
            self._boxes.append(DebugBox(
                x, y, w, h, color, alpha, duration,
                label, text_color, font_scale, thickness
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

    def draw_boxes(self, image: np.ndarray) -> np.ndarray:
        """在图像上绘制所有当前调试框及其文字标签"""
        self._clear_expired()
        with self._lock:
            if self._boxes:
                print(self._boxes)
            for box in self._boxes:
                # 半透明矩形框
                overlay = image.copy()
                cv2.rectangle(overlay, box.top_left, box.bottom_right, box.color, -1)
                image = cv2.addWeighted(overlay, box.alpha, image, 1 - box.alpha, 0)

                # 添加文字标签（可选）
                if box.label:
                    x, y = box.top_left
                    cv2.putText(
                        image,
                        box.label,
                        (x + 3, y - 5 if y - 5 > 10 else y + 15),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        box.font_scale,
                        box.text_color,
                        box.thickness,
                        lineType=cv2.LINE_AA,
                    )
        return image
