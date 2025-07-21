from copy import copy
from dataclasses import dataclass
from typing import List

import cv2
import numpy as np

from src.entity.Yolo import Yolo_Box
from src.utils.logger import logger
from src.utils.ocr_instance import OCRService
from src.utils.opencv_tools import check_status_detection

ocr_service = OCRService()


@dataclass
class TabBarItem(Yolo_Box):
    text: str

    def __init__(self, x: float, y: float, w: float, h: float, text: str, frame):
        self.text = text
        x = int(x)
        y = int(y)
        w = int(w)
        h = int(h)
        super().__init__(x, y, w, h, "TabBarItem", frame)


@dataclass
class TabBar(Yolo_Box):
    tab_items: List[TabBarItem]
    selected: TabBarItem = None

    def __init__(self, element: Yolo_Box):
        super().__init__(element.x, element.y, element.w, element.h, element.label, element.frame)
        # self.tab_items = [
        #     TabBarItem(item.x, item.y, item.w, item.h, item.text, element)
        #     for item in ocr_service.ocr(element.frame)
        #     if len(item.text) > 2
        # ]
        self.tab_items = self._get_items()
        for tab_item in self.tab_items:
            if check_status_detection(tab_item.frame):
                self.selected = tab_item
                break

    def _get_items(self) -> List[TabBarItem]:
        target_x, target_y, _ = self.frame.shape

        img = copy(self.frame)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        # 取色 抠图
        mask_orange = cv2.inRange(hsv, (5, 85, 250), (18, 255, 255))
        mask_gary = cv2.inRange(hsv, (0, 0, 0), (0, 0, 185))
        black = np.array([0, 0, 0])  # BGR格式
        white = np.array([255, 255, 255])
        mask_combined = cv2.bitwise_or(mask_orange, mask_gary)
        img[mask_combined > 0] = black
        img[~(mask_orange > 0) & ~(mask_gary > 0)] = white

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # 膨胀，使同一词内字符连接
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 5))  # 横向拉长
        dilated = cv2.dilate(binary, kernel, iterations=1)

        # 查找词块轮廓
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # 提取词块并排序
        word_boxes = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            if w > 20 and h > 10:  # 过滤噪声
                word_boxes.append((x, y, w, h))
        word_boxes = sorted(word_boxes, key=lambda b: b[0])  # 按x排序
        logger.debug(f"word_boxes={word_boxes}")
        tab_items = []
        if len(word_boxes) <= 2:
            tab_items = [
                TabBarItem(
                    el_x := self.x + item.x,
                    el_y := self.y + item.y,
                    el_w := el_x + item.w,
                    el_h := el_y + item.h,
                    item.text,
                    self.frame[el_y:el_h, el_x:el_w]
                )
                for item in ocr_service.ocr(img)
                if len(item.text) > 2
            ]
        else:
            for i, (x, y, w, h) in enumerate(word_boxes):
                cropped = img[y:y + h, x:x + w]
                ocr_results = ocr_service.ocr(cropped)
                tab_items.append(TabBarItem(
                    el_x := self.x + x,
                    el_y := self.y + y,
                    el_w := el_x + w,
                    el_h := el_y + h,
                    "".join([item.text for item in ocr_results]),
                    self.frame[el_y:el_h, el_x:el_w]
                ))
        logger.debug(f"tab_items=\n{tab_items}")
        return tab_items

    def __iter__(self):
        return iter(self.tab_items)

    def __bool__(self):
        return bool(self.tab_items)

    def __len__(self):
        return len(self.tab_items)
