import re
from dataclasses import dataclass
from typing import List

import cv2
import numpy as np

from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.entity.Yolo import Yolo_Box, Yolo_Results
from src.core.inference.ocr_engine import OCRService, OCR_Result

ocr_service = OCRService()

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
    _width: float

    def __init__(self, results: Yolo_Results, frame: np.ndarray):
        _, self._width = frame.shape[:2]
        if not results.filter_by_label(BaseUILabels.BUTTON):
            return
        self._start_y = results.filter_by_label(BaseUILabels.BUTTON).get_y_max_element().first().h
        self._end_y = results.filter_by_label(BaseUILabels.BACK_BTN).first().y
        self.contest_area = frame[self._start_y:self._end_y, 0:self._width]
        if self.contest_area.size == 0:
            return
        if not [res for res in ocr_service.ocr(self.contest_area) if "消費しました" in res.text]:
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
        self.contests = []
        hsv = cv2.cvtColor(self.contest_area, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (90,0,120), (104,255,142))
        # 闭运算连接碎块
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        # 膨胀扩大连通区域
        mask = cv2.dilate(mask, kernel, iterations=1)
        # cv2.imshow("mask", mask)
        # 查找轮廓
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        # result = self.contest_area.copy()
        # 依次提取每个区域
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)

            # 筛选条件 宽度必须大于帧宽度的一半
            if w > self._width * 0.5 and h > 30:
                roi = self.contest_area[y:y+h, x:x+w]
                self._append_contest(x, box_y := self._start_y+y, x+w, box_y+h, roi)
                # cv2.drawContours(result, [cnt], -1, (0, 255, 0), 2)
                continue
        #     cv2.drawContours(result, [cnt], -1, (0, 0, 255), 2)
        # cv2.imshow("Contours - Filtered", result)
        # cv2.waitKey(0)

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