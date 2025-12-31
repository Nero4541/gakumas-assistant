from copy import copy
from dataclasses import dataclass
from typing import List

import cv2
import numpy as np

from src.entity.Yolo import Yolo_Box
from src.utils.debug_tools import DebugTools
from src.utils.logger import logger
from src.core.inference.ocr_engine import OCRService
from src.utils.opencv_tools import check_status_detection

ocr_service = OCRService()
debug_tools = DebugTools()

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
        cv2.imwrite("tabbar.png", self.frame)
        self.tab_items = self._get_items()
        for tab_item in self.tab_items:
            if check_status_detection(tab_item.frame):
                self.selected = tab_item
                break

    def _get_items(self) -> List[TabBarItem]:
        height, width, _ = self.frame.shape
        img = copy(self.frame)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        # 取色 抠图
        mask_orange = cv2.inRange(hsv, (0, 50, 0), (179, 255, 255))
        mask_gray = cv2.inRange(hsv, (0, 0, 0), (0, 0, 190))
        mask_combined = cv2.bitwise_or(mask_orange, mask_gray)
        processed_img = np.full(img.shape, 255, dtype=np.uint8)
        processed_img[mask_combined > 0] = [0, 0, 0] # 目标区域变黑
        gray = cv2.cvtColor(processed_img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3))
        morphed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        morphed = cv2.dilate(morphed, kernel, iterations=1)
        contours, _ = cv2.findContours(morphed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        # 提取词块并排序
        word_boxes = []
        offset = 5
        y_offset_limit = height // 6
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            if w > 20:
                current_center_y = y + h / 2
                if abs(current_center_y - height // 2) > y_offset_limit:
                    continue
                word_boxes.append((x-offset, y-offset, w+offset, h+offset))
        word_boxes = sorted(word_boxes, key=lambda b: b[0])  # 按x排序
        logger.debug(word_boxes)
        tab_items = []
        for i, (x, y, w, h) in enumerate(word_boxes):
            cropped = img[y:y + h, x:x + w]
            ocr_results = ocr_service.ocr(cropped)
            text = "".join([item.text for item in ocr_results])
            tab_items.append(TabBarItem(
                el_x := self.x + x,
                el_y := self.y + y,
                el_w := el_x + w,
                el_h := el_y + h,
                text,
                self.frame[el_y:el_h, el_x:el_w]
            ))
            debug_tools.add_box(el_x, el_y, el_w, el_h, label=text)
        logger.debug(tab_items)
        return tab_items

    def __iter__(self):
        return iter(self.tab_items)

    def __bool__(self):
        return bool(self.tab_items)

    def __len__(self):
        return len(self.tab_items)
