import re
from dataclasses import dataclass
from typing import List

import cv2
import numpy as np
from copy import copy

from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.entity.Yolo import Yolo_Box, Yolo_Results
from src.core.inference.ocr_engine import OCRService, OCR_Result
from src.utils.debug_tools import DebugTools
from src.utils.opencv_tools import gen_color_mask, filter_by_rectangle_shape
from src.utils.string_tools import string_match, MatchConfig
from src.utils.logger import logger

ocr_service = OCRService()
debug_tools = DebugTools()

@dataclass
class ContestItem(Yolo_Box):
    combat_power: int
    pt: int
    username: str

    def __init__(self, x: float, y: float, w: float, h: float, label: str, frame: np.ndarray):
        super().__init__(x, y, w, h, label, frame)
        ocr_result = ocr_service.ocr(frame)
        self._parse_ocr_results(ocr_result)

    def _parse_ocr_results(self, ocr_results: List[OCR_Result]):
        # 1. 找 “総合力合計” 作为 combat_power 的锚点
        power_anchor = next((r for r in ocr_results if "総合力合計" in r.text), None)
        if not power_anchor:
            raise ValueError("找不到[総合力合計]锚点")

        # 2. pt：最靠右上角的一个（y 最小，其次 x 最大）
        pt_result = min(ocr_results, key=lambda r: (r.y, -r.x))
        digits = re.findall(r'\d+', pt_result.text.replace("O", "0"))
        pt = int(digits[0]) if digits else 0

        lower_results = [r for r in ocr_results if r.y > power_anchor.y]
        combat_power_result = min(lower_results, key=lambda r: r.y, default=None)
        digits = re.findall(r'\d+', combat_power_result.text.replace("O", "0")) if combat_power_result else []
        combat_power = int(digits[0]) if digits else None

        # 4. username：最靠左下角（y 最大，其次 x 最小）
        username_result = max(ocr_results, key=lambda r: (r.y, -r.x))
        username = username_result.text

        self.pt = pt
        self.combat_power = combat_power
        self.username = username

class ContestList:
    contests: List[ContestItem] = []
    contest_area: np.ndarray
    _start_y: float
    _end_y: float

    def __init__(self, results: Yolo_Results, frame: np.ndarray):
        _, width, _ = frame.shape
        if not results.filter_by_label(BaseUILabels.BUTTON):
            logger.debug("Not find button")
            return
        self._start_y = results.filter_by_label(BaseUILabels.BUTTON).get_y_max_element().first().h
        self._end_y = results.filter_by_label(BaseUILabels.BACK_BTN).first().y
        logger.debug(f"start_y={self._start_y}, end_y={self._end_y}")
        self.contest_area = frame[self._start_y:self._end_y, 0:width]
        if self.contest_area is None or self.contest_area.size == 0:
            logger.debug("No contest area")
            return
        contest_area_ocr = "".join([res.text for res in ocr_service.ocr(self.contest_area)])
        if string_match(contest_area_ocr, "消費しました", MatchConfig(fuzz_threshold=70)):
            logger.debug("Today's challenge opportunities have all been used up")
            return
        self.contests = []
        self._get_contest_items()

    def __str__(self):
        return str(self.contests)

    def __len__(self):
        return len(self.contests)

    def __iter__(self):
        return iter(self.contests)

    def __bool__(self):
        return bool(self.contests)

    def _append_contest(self, x: float, y: float, w: float, h: float, frame: np.ndarray):
        self.contests.append(ContestItem(x, y, w, h, f"contest_{len(self.contests) + 1}",frame))

    def _get_contest_items(self):
        height, width, _ = self.contest_area.shape
        total_pixels = height * width  # 总像素数

        # 灰色
        lower1 = (0,0,75)
        upper1 = (179,75,140)
        # 白色
        lower2 = (0,0,235)
        upper2 = (179,15,255)

        mask1 = gen_color_mask(self.contest_area, lower1, upper1)
        mask2 = gen_color_mask(self.contest_area, lower2, upper2)
        mask = cv2.bitwise_or(mask1, mask2)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3,3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        # mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.dilate(mask, kernel, iterations=2)
        result = copy(self.contest_area)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        # contours = filter_by_rectangle_shape(contours, total_pixels // 4)
        # 依次提取每个区域
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            # 筛选条件 宽度必须大于帧宽度的一半
            if w > width * 0.5:
                roi = self.contest_area[y:y+h, x:x+w]
                self._append_contest(x, box_y := self._start_y+y, x+w, box_y+h, roi)
                cv2.drawContours(result, [cnt], -1, (0, 255, 0), 2)
                debug_tools.add_box(x, box_y := int(self._start_y+y), x+w, box_y+h, color=(127,255,0))
                continue
            cv2.drawContours(result, [cnt], -1, (0, 0, 255), 2)
            debug_tools.add_box(x, box_y := int(self._start_y+y), x+w, box_y+h, color=(255,0,0))

    def _get_valid_contests(self) -> List[ContestItem]:
        return [r for r in self.contests if r.combat_power is not None]

    def get_combat_power_min(self):
        return min(self._get_valid_contests(), key=lambda r: r.combat_power, default=None)

    def get_combat_power_max(self):
        return max(self._get_valid_contests(), key=lambda r: r.combat_power, default=None)

    def get_pt_min(self):
        return min(self._get_valid_contests(), key=lambda r: r.pt, default=None)

    def get_pt_max(self):
        return max(self._get_valid_contests(), key=lambda r: r.pt, default=None)