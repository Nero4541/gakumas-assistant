import os.path
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from threading import Lock
from time import time
from typing import Tuple, List, Optional, Union

import cv2
import numpy as np

from src.entity.Base import SingletonMeta
from src.utils.opencv_tools import draw_text

@dataclass
class DebugElement(ABC):
    """调试元素的抽象基类"""
    color: Tuple[int, int, int]
    alpha: float
    duration: float
    created_at: float = field(default_factory=time)

    @property
    def expire_time(self) -> float:
        return self.created_at + self.duration

    @abstractmethod
    def draw(self, overlay_img: np.ndarray, final_img: np.ndarray):
        """
        绘制元素。
        :param overlay_img: 用于绘制半透明背景的图层
        :param final_img: 最终输出的图像（用于绘制不透明的实体线条或文字）
        """
        pass


@dataclass
class DebugBox(DebugElement):
    x: int = 0
    y: int = 0
    w: int = 0  # 右下角 x
    h: int = 0  # 右下角 y
    label: Optional[str] = None
    text_color: Tuple[int, int, int] = (255, 255, 255)
    font_size: int = 22
    thickness: int = 2

    color: Tuple[int, int, int] = (0, 0, 255)
    alpha: float = 0.4
    duration: float = 60.0

    def __post_init__(self):
        # 简单的坐标验证，确保 w>x, h>y
        self.x, self.w = min(self.x, self.w), max(self.x, self.w)
        self.y, self.h = min(self.y, self.h), max(self.y, self.h)

    @property
    def top_left(self) -> Tuple[int, int]:
        return self.x, self.y

    @property
    def bottom_right(self) -> Tuple[int, int]:
        return self.w, self.h

    def draw(self, overlay_img: np.ndarray, final_img: np.ndarray):
        # 绘制半透明矩形填充
        cv2.rectangle(overlay_img, self.top_left, self.bottom_right, self.color, -1)
        # 绘制边框
        cv2.rectangle(final_img, self.top_left, self.bottom_right, self.color, self.thickness)

        if self.label:
            font_path = os.path.join(os.getcwd(), "assets/NotoSerifCJKsc-Medium.otf")
            x, y = self.top_left
            final_img[:] = draw_text(
                final_img,
                self.label,
                (x,y),
                font_path,
                self.font_size,
                self.text_color,
                self.w - self.x,
                line_spacing=self.thickness,
                center=True
            )
        # cv2.imshow("text", final_img)


@dataclass
class DebugLine(DebugElement):
    start_x: int = 0
    start_y: int = 0
    end_x: int = 0
    end_y: int = 0
    thickness: int = 2
    padding: int = 5  # 线条背景光晕宽度

    color: Tuple[int, int, int] = (0, 255, 0)
    alpha: float = 0.5
    duration: float = 60.0

    def draw(self, overlay_img: np.ndarray, final_img: np.ndarray):
        # 1. 在 overlay 上绘制较粗的半透明线条作为光晕背景
        cv2.line(
            overlay_img,
            (self.start_x, self.start_y), (self.end_x, self.end_y),
            self.color,
            self.thickness + self.padding * 2 # 背景比线条本身粗
        )
        # 2. 在 final 上绘制实体线条
        cv2.line(
            final_img,
            (self.start_x, self.start_y), (self.end_x, self.end_y),
            self.color,
            self.thickness
        )


@dataclass
class DebugPoint(DebugElement):
    """调试关键点"""
    cx: int = 0
    cy: int = 0
    radius: int = 5
    thickness: int = -1 # -1 表示填充实心
    padding: int = 8 # 光晕大小

    color: Tuple[int, int, int] = (0, 255, 255) # 默认黄色
    alpha: float = 0.6
    duration: float = 60.0

    def draw(self, overlay_img: np.ndarray, final_img: np.ndarray):
        center = (self.cx, self.cy)
        # Overlay 绘制半透明大圆光晕
        cv2.circle(overlay_img, center, self.radius + self.padding, self.color, -1)
        # Final 绘制中心实心亮点
        cv2.circle(final_img, center, self.radius, (255, 255, 255), self.thickness) # 中心白色高亮
        cv2.circle(final_img, center, self.radius, self.color, 1) # 外圈自身颜色描边

class DebugTools(metaclass=SingletonMeta):
    _elements: List[DebugElement] = []
    _lock: Lock = Lock()
    _hide: bool = False
    _show_grid: bool = False # 新增：是否显示网格的开关

    def add_box(self, x: int, y: int, w: int, h: int, **kwargs):
        """绘制调试框 (x, y, end_x, end_y)"""
        with self._lock:
            self._elements.append(DebugBox(x=x, y=y, w=w, h=h, **kwargs))

    def add_line(self, start_x: int, start_y: int, end_w: int, end_h: int, **kwargs):
        """绘制调试线 (start_x, start_y, end_x, end_y)"""
        with self._lock:
            self._elements.append(DebugLine(
                start_x=start_x, start_y=start_y, end_x=end_w, end_y=end_h, **kwargs
            ))

    def add_point(self, cx: int, cy: int, **kwargs):
        """新增：绘制调试关键点 (center_x, center_y)"""
        with self._lock:
            self._elements.append(DebugPoint(cx=cx, cy=cy,**kwargs))

    def add_crosshair(self, x: int, y: int, size: int = 30, color=(0, 0, 255), thickness=1, **kwargs):
        """新增：绘制十字准星，用于精确定位"""
        half = size // 2
        # 利用 add_line 组合
        common_kwargs = {'color': color, 'thickness': thickness, **kwargs}
        self.add_line(x - half, y, x + half, y, duration=3, **common_kwargs) # 水平线
        self.add_line(x, y - half, x, y + half, duration=3, **common_kwargs) # 垂直线

    def add_trajectory(self, points: List[Tuple[int, int]], color=(255, 100, 0), thickness=2, **kwargs):
        """新增：绘制轨迹路径"""
        if len(points) < 2:
            return
        for i in range(len(points) - 1):
            p1 = points[i]
            p2 = points[i+1]
            self.add_line(p1[0], p1[1], p2[0], p2[1], color=color, thickness=thickness, **kwargs)

    def _clear_expired(self):
        now = time()
        with self._lock:
            self._elements = [el for el in self._elements if el.expire_time > now]

    def clear_all(self):
        with self._lock:
            self._elements = []

    def hide(self):
        with self._lock:
            self._hide = True

    def show(self):
        with self._lock:
            self._hide = False

    def toggle_grid(self, show: bool = None):
        """切换网格显示"""
        with self._lock:
            if show is None:
                self._show_grid = not self._show_grid
            else:
                self._show_grid = show

    def _draw_grid_overlay(self, image: np.ndarray, step: int = 50, color=(128, 128, 128)):
        """绘制网格辅助线"""
        h, w = image.shape[:2]
        overlay = image.copy()
        # 绘制垂直线
        for x in range(0, w, step):
            thickness = 2 if x == 0 else 1
            cv2.line(overlay, (x, 0), (x, h), color, thickness)
        # 绘制水平线
        for y in range(0, h, step):
            thickness = 2 if y == 0 else 1
            cv2.line(overlay, (0, y), (w, y), color, thickness)

        # 绘制中心十字
        cv2.line(overlay, (w//2, 0), (w//2, h), (0, 0, 255), 1)
        cv2.line(overlay, (0, h//2), (w, h//2), (0, 0, 255), 1)

        return cv2.addWeighted(overlay, 0.3, image, 0.7, 0)

    def draw_boxes(self, image: np.ndarray) -> np.ndarray:
        """主绘制方法"""
        # 绘制网格（如果开启）
        if self._show_grid:
            image = self._draw_grid_overlay(image)

        self._clear_expired()
        if self._hide or not self._elements:
            return image

        final_image = image.copy()
        overlay_image = image.copy()

        with self._lock:
            for el in self._elements:
                el.draw(overlay_image, final_image)
            # 统一应用半透明混合
            image_with_overlay = cv2.addWeighted(overlay_image, 0.5, final_image, 0.5, 0)

            mask = np.any(final_image != image, axis=2)
            image_with_overlay[mask] = final_image[mask]

            return image_with_overlay


if __name__ == '__main__':
    # 创建一个黑色背景图用于测试
    canvas = np.zeros((600, 800, 3), dtype=np.uint8)
    debugger = DebugTools()

    # 1. 测试 Box (带居中标签)
    debugger.add_box(100, 100, 300, 300, label="目标 Target", color=(0, 0, 255), font_size=50)

    # 2. 测试 Line (带背景光晕)
    debugger.add_line(400, 50, 700, 150, color=(0, 255, 0), thickness=3)

    # 3. 测试 Point (关键点)
    debugger.add_point(600, 400, radius=8, color=(255, 0, 255)) # 紫色关键点
    debugger.add_point(650, 420, radius=5, color=(0, 255, 255)) # 黄色关键点

    # 4. 测试十字准星 (组合工具)
    debugger.add_crosshair(400, 300, size=50, color=(255, 255, 0), thickness=2) # 画面中心黄色准星

    # 5. 测试轨迹 (组合工具)
    trajectory_points = [(50, 400), (100, 420), (150, 450), (200, 430), (250, 500)]
    debugger.add_trajectory(trajectory_points, color=(50, 100, 255), thickness=2)

    # 6. 测试网格开关
    debugger.toggle_grid(True)

    # 执行绘制
    result_image = debugger.draw_boxes(canvas)

    # 显示结果
    cv2.imshow("Debug Tools Demo", result_image)
    cv2.waitKey(0)
    cv2.destroyAllWindows()