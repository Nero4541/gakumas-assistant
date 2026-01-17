import re
import threading
from dataclasses import dataclass
from typing import List

import cv2
import numpy as np

from src.entity.Base import SingletonMeta
from src.entity.Yolo import Yolo_Box
from src.utils.dml_manager import DMLManager
from src.utils.logger import logger

from rapidocr import RapidOCR, EngineType, LangDet, LangRec, ModelType, OCRVersion

from src.utils.opencv_tools import letterbox
from src.utils.performance_tools import timeit
from src.utils.string_tools import fullwidth_to_halfwidth, MatchConfig, string_match


class OCRLoader(metaclass=SingletonMeta):
    _instance = None
    _infer_lock = threading.Lock()

    def __init__(self):
        # 初始化时创建 RapidOCR 实例
        self.ocr = RapidOCR(
            params={
                "EngineConfig.onnxruntime.use_dml": True,
                "Global.use_cls": False,
                "Global.min_height": 10,

                "Det.engine_type": EngineType.ONNXRUNTIME,
                "Det.lang_type": LangDet.CH,
                "Det.model_type": ModelType.MOBILE,
                "Det.ocr_version": OCRVersion.PPOCRV5,

                "Rec.engine_type": EngineType.ONNXRUNTIME,
                "Rec.lang_type": LangRec.JAPAN,
                "Rec.model_type": ModelType.MOBILE,
            },
        )

    def __call__(self, *args, **kwargs):
        with self._infer_lock:
            return self.ocr(*args, **kwargs)

@dataclass
class OCR_Result(Yolo_Box):

    text: str
    confidence: float

    def __init__(self, x, y, w, h, text, confidence):
        super().__init__(x, y, w, h, None, None)
        self.text = text
        self.confidence = confidence

    def __eq__(self, other):
        if not isinstance(other, OCR_Result):
            return False
        return (self.x == other.x and self.y == other.y and self.w == other.w and
                self.h == other.h and self.text == other.text and self.confidence == other.confidence)

    def __hash__(self):
        return hash((self.x, self.y, self.w, self.h, self.text, self.confidence))

@dataclass
class OCR_ResultList:
    results: List[OCR_Result]

    def __init__(self, results: List[OCR_Result]):
        self.results = results

    def __bool__(self):
        return bool(self.results)

    def __len__(self):
        return len(self.results)

    def __iter__(self):
        return iter(self.results)

    def get_y_min(self) -> "OCR_Result":
        """返回Y轴最小的（最靠上）"""
        return min(self.results, key=lambda box: box.y)

    def get_y_max(self) -> "OCR_Result":
        """返回Y轴最小的（最靠下）"""
        return max(self.results, key=lambda box: box.h)

    def get_x_min(self) -> "OCR_Result":
        """返回X轴最小的（最靠左）"""
        return min(self.results, key=lambda box: box.x)

    def get_x_max(self) -> OCR_Result:
        """"返回X轴最大的（最靠右）"""
        return max(self.results, key=lambda box: box.w)

    def first(self) -> OCR_Result:
        return self.results[0]

    @classmethod
    def _from(cls, results: List[OCR_Result]):
        inst = cls.__new__(cls)
        inst.results = results
        return inst


    def auto_merge_lines(self, cy_range: float = 3, width_gap: float = 10) -> 'OCR_ResultList':
        """
        自动合并行
        :param cy_range: 行之间的中心距离
        :param width_gap: 横向间距
        :return: 合并后的OCR结果列表
        """
        merged_results = []
        current_line = []
        prev_result = None

        for result in self.results:
            if prev_result:
                # 判断是否在同一行，且横向距离合适
                if abs(result.cy - prev_result.cy) <= cy_range and (result.x - prev_result.x - prev_result.w) <= width_gap:
                    # 如果在同一行，且横向间距符合条件，加入到当前行
                    current_line.append(result)
                else:
                    # 如果不在同一行，合并当前行
                    merged_text = ' '.join([r.text for r in current_line])
                    # 合并当前行的宽度
                    merged_width = current_line[-1].x + current_line[-1].w - current_line[0].x
                    merged_results.append(OCR_Result(
                        x=current_line[0].x,
                        y=current_line[0].y,
                        w=merged_width,
                        h=current_line[0].h,
                        text=merged_text,
                        confidence=None
                    ))
                    current_line = [result]  # 开始新的一行
            else:
                # 第一行直接加入
                current_line.append(result)

            prev_result = result

        # 合并最后一行
        if current_line:
            merged_text = ' '.join([r.text for r in current_line])
            merged_width = current_line[-1].x + current_line[-1].w - current_line[0].x
            merged_results.append(OCR_Result(
                x=current_line[0].x,
                y=current_line[0].y,
                w=merged_width,
                h=current_line[0].h,
                text=merged_text,
                confidence=None
            ))

        return self._from(merged_results)

    @staticmethod
    def calculate_confidence(current_line: List[OCR_Result]) -> float:
        """
        计算平均信心值
        :param current_line: 当前行的OCR结果列表
        :return: 平均信心值
        """
        return sum(r.confidence for r in current_line) / len(current_line)  # 取平均信心值

    def exclude(self, exclude_list: List[OCR_Result]) -> 'OCR_ResultList':
        """
        排除指定OCR结果并返回新的OCR_ResultList
        :param exclude_list: 要排除的OCR_Result列表
        :return:
        """
        # 返回不包含指定OCR结果的新列表
        new_results = [result for result in self.results if result not in exclude_list]
        return self._from(new_results)

    def search(self, query: str | list[str], config: MatchConfig = None) -> 'OCR_ResultList':
        """
        使用 string_match 查询 OCR 结果
        :param query: 查询关键字或列表
        :param config: 匹配配置
        :return: OCR_ResultList
        """
        if config is None:
            config = MatchConfig()

        matched_results = []
        for result in self.results:
            match_result = string_match(result.text, query, config)
            if match_result:
                matched_results.append(result)

        return self._from(matched_results)



class OCRService:
    ocr_engine: OCRLoader
    def __init__(self):
        self.ocr_engine = OCRLoader()

    @classmethod
    def _map_result_to_ocr_result(cls, result, ratio: float, dw: float, dh:float) -> List[OCR_Result]:
        if result is None or result.boxes is None:
            return []

        temp = []
        for box, text, score in zip(result.boxes, result.txts, result.scores):
            x, y, w, h = cv2.boundingRect(box.astype(np.int32))
            x = (x - dw) / ratio
            y = (y - dh) / ratio
            w = w / ratio
            h = h / ratio
            temp.append(OCR_Result(
                x=int(x),
                y=int(y),
                w=int(w),
                h=int(h),
                text=fullwidth_to_halfwidth(text),
                confidence=score
            ))
        return temp

    @timeit
    def ocr(self, img: np.ndarray):
        if img.size == 0:
            logger.warning(f"Empty images or dimensions are illegal: {img.shape if img is not None else 'None'}")
            return []
        img_letterbox, ratio, (dw, dh) = letterbox(img)
        with DMLManager.get_lock():
            result = self.ocr_engine(img_letterbox, use_cls=False)
        result = self._map_result_to_ocr_result(result, ratio, dw, dh)
        return OCR_ResultList(result)