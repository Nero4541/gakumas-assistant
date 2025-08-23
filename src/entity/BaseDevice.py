import abc

import numpy as np

from src.entity.Yolo import Yolo_Box, Yolo_Results


class BaseDevice(abc.ABC):

    def is_app_focused(self):
        pass

    def capture(self) -> np.ndarray:
        """
        截取游戏画面
        :return:
        """

    def click(self, x, y, el_label = ""):
        """
        点击窗口内容（坐标）
        :param x: x轴窗口内坐标
        :param y: y轴窗口内坐标
        :param el_label: 标签（debug用）
        :return:
        """

    def click_element(self, element: Yolo_Box | Yolo_Results):
        """
        点击窗口内容（元素）
        :param element: Yolo_Box | Yolo_Results
        :return:
        """
        self.click(*element.get_COL(), getattr(element, "label", ""))

    def scrollY(self, x, y, scroll_delta):
        """
        向下滚动窗口
        :param x: x轴窗口内坐标
        :param y: y轴窗口内坐标
        :param scroll_delta: 滚动距离（各系统可能不大相同）
        :return:
        """