import ast
import colorsys
import os
import json
import threading
from dataclasses import dataclass
from typing import List, Tuple, Generator, Optional, Union, Dict

import numpy as np
import cv2
import onnxruntime as ort

from src.utils.dml_manager import DMLManager
from src.utils.logger import logger
from src.utils.opencv_tools import letterbox, center_crop


@dataclass
class ONNXYoloModelMeta:
    imgsz: Tuple[int, int]
    names: Dict[int, str]
    colors: Dict[int, Tuple[int, int, int]]

@dataclass
class ONNXYoloResult:
    boxes: np.ndarray
    scores: np.ndarray
    class_ids: np.ndarray
    model_mata: ONNXYoloModelMeta
    image: np.ndarray

    def __bool__(self):
        return bool(self.boxes.size > 0)

    def __len__(self):
        return len(self.boxes)

    def __iter__(self):
        return iter(self.boxes)

    def plot(
            self,
            line_width: int = 2,
            font_size: float = 0.5,
    ) -> np.ndarray:
        img = self.image.copy()
        for box, score, cls in zip(self.boxes, self.scores, self.class_ids):
            x, y, w, h = box.astype(int)
            color = self.model_mata.colors.get(cls, (0, 255, 0))
            cv2.rectangle(img, (x, y), (x + w, y + h), color, line_width)
            label = f"{self.model_mata.names.get(cls, cls)}: {score:.2f}"
            # 计算标签文本的尺寸
            (label_width, label_height), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_size, 1)
            label_x = x
            label_y = y - 10 if y - 10 > label_height else y + 10
            cv2.rectangle(img, (label_x, label_y - label_height), (label_x + label_width, label_y + label_height), color, cv2.FILLED)
            cv2.putText(img, label, (label_x, label_y), cv2.FONT_HERSHEY_SIMPLEX, font_size, (0, 0, 0), 1, cv2.LINE_AA)
        return img

class YoloModelFromONNX:
    _model_meta: ONNXYoloModelMeta
    _engine: ort.InferenceSession
    _model_dir: str
    _model_file: str
    _model_name: str
    _model_input_name: str
    def __init__(self, model_path: str) -> None:
        """
        初始化ONNX模型
        :param model_path: 模型地址
        """
        if not os.path.exists(model_path) or not os.path.isfile(model_path):
            raise FileNotFoundError(model_path)
        self._model_dir, self._model_file = os.path.split(model_path)
        self._model_name = os.path.splitext(self._model_file)[0]
        self._load_model_meta()
        self._engine = DMLManager.create_dml_session(model_path)
        self._model_input_name = self._engine.get_inputs()[0].name

    @staticmethod
    def _pastel_palette(n: int):
        colors = []
        for i in range(n):
            h = i / n
            s = 0.45      # 更柔
            v = 0.95
            r, g, b = colorsys.hsv_to_rgb(h, s, v)
            colors.append((int(r*255), int(g*255), int(b*255)))
        return colors

    def _load_model_meta(self):
        meta_path = os.path.join(self._model_dir, f"{self._model_name}_meta.json")
        with open(meta_path, "r") as f:
            meta = json.load(f)
        imgsz = json.loads(meta["imgsz"])
        names_mapping = ast.literal_eval(meta["names"])
        palette_255 = self._pastel_palette(len(names_mapping))
        logger.debug(palette_255)
        color_mapping = {
            name_id: color
            for name_id, color in zip(names_mapping.keys(), palette_255)
        }
        self._model_meta = ONNXYoloModelMeta(imgsz, names_mapping, color_mapping)

    def _preprocess(self, img: np.ndarray) -> Tuple[np.ndarray, float, float, float]:
        """
        图像预处理
        :param img: 图像
        :return:
        """
        img_letterbox, ratio, (dw, dh) = letterbox(img, self._model_meta.imgsz)
        img_rgb = cv2.cvtColor(img_letterbox, cv2.COLOR_BGR2RGB)
        img_rgb = img_rgb.astype(np.float32) / 255.0
        img_rgb = img_rgb.transpose(2, 0, 1)
        return np.expand_dims(img_rgb, axis=0), ratio, dw, dh

    def _postprocess(
            self,
            input_image: np.ndarray,
            results: np.ndarray,
            conf_threshold: float,
            iou_threshold: float,
            ratio: float,
            dw: float,
            dh: float
    ) -> ONNXYoloResult:
        """
        后处理模型输出
        :param input_image: 输入图像
        :param results: 模型推理结果
        :param conf_threshold: 得分阈值
        :param iou_threshold: NMS阈值
        :return:
        """
        outputs = np.transpose(np.squeeze(results[0]))
        # 获取输出数组的行数
        rows = outputs.shape[0]
        # 存储检测到的边界框、分数和类别ID的列表
        boxes = []
        scores = []
        class_ids = []
        # 计算边界框坐标的比例因子
        h, w, _ = input_image.shape
        for i in range(rows):
            # 从当前行提取类别的得分
            classes_scores = outputs[i][4:]
            # 找到类别得分中的最大值
            max_score = np.amax(classes_scores)

            if max_score >= conf_threshold:
                class_id = np.argmax(classes_scores)
                x, y, w, h = outputs[i][0], outputs[i][1], outputs[i][2], outputs[i][3]

                # 将中心坐标转为左上角
                left = x - w / 2
                top = y - h / 2

                # 还原到 letterbox 前的坐标
                left = (left - dw) / ratio
                top = (top - dh) / ratio
                width = w / ratio
                height = h / ratio

                class_ids.append(class_id)
                scores.append(max_score)
                boxes.append([left, top, width, height])

        nms_boxes = []
        nms_scores = []
        nms_class_ids = []

        # 获取所有类别的唯一类别 ID
        unique_class_ids = np.unique(class_ids)

        for class_id in unique_class_ids:
            # 获取当前类别的所有框、分数和类别ID
            class_boxes = [boxes[i] for i in range(len(boxes)) if class_ids[i] == class_id]
            class_scores = [scores[i] for i in range(len(scores)) if class_ids[i] == class_id]
            class_class_ids = [class_ids[i] for i in range(len(class_ids)) if class_ids[i] == class_id]

            # 应用 NMS
            indices = cv2.dnn.NMSBoxes(class_boxes, class_scores, conf_threshold, iou_threshold)

            # 保存当前类别的 NMS 结果
            nms_boxes.extend([class_boxes[i] for i in indices])
            nms_scores.extend([class_scores[i] for i in indices])
            nms_class_ids.extend([class_class_ids[i] for i in indices])

        return ONNXYoloResult(
            np.array(nms_boxes),
            np.array(nms_scores),
            np.array(nms_class_ids),
            self._model_meta,
            input_image
        )

    def __call__(self, img: np.ndarray, conf_threshold: float = 0.5, iou_threshold: float = 0.5) -> ONNXYoloResult:
        input_tensor, ratio, dw, dh = self._preprocess(img)
        outputs = DMLManager.run(
            self._engine,
            {self._model_input_name: input_tensor}
        )
        return self._postprocess(img, outputs, conf_threshold, iou_threshold, ratio, dw, dh)

class CLIPModelFromONNX:
    session: ort.InferenceSession
    _input_name: str
    _lock: threading.Lock

    def __init__(self, model_path: str=None):
        if not model_path or not os.path.exists(model_path):
            model_path = os.path.join(os.getcwd(), "model", "clip_visual.onnx")
        self.session = DMLManager.create_dml_session(model_path)
        self._input_name = self.session.get_inputs()[0].name
        self._lock = threading.Lock()

    @staticmethod
    def _preprocess(image: np.ndarray) -> np.ndarray:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        image, _, (_, _) = letterbox(image, (224, 224))
        image = center_crop(image)
        image = image.astype(np.float32) / 255.0
        mean = np.array([0.48145466, 0.4578275, 0.40821073]).reshape(1, 1, 3)
        std = np.array([0.26862954, 0.26130258, 0.27577711]).reshape(1, 1, 3)
        image = (image - mean) / std
        image = np.transpose(image, (2, 0, 1))  # [HWC] -> [CHW]
        return image[np.newaxis, :].astype(np.float32)

    def forward(self, image: np.ndarray) -> Optional[np.ndarray]:
        input_tensor = self._preprocess(image)
        try:
            output = DMLManager.run(
                self.session,
                {self._input_name: input_tensor}
            )
            return output[0]
        except Exception as e:
            logger.error(e)
            return None