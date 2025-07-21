import ast
import os
import json
import threading
from dataclasses import dataclass
from typing import List, Tuple, Generator, Optional, Union, Dict

import numpy as np
import cv2
import onnxruntime as ort

from src.utils.logger import logger
from src.utils.opencv_tools import letterbox


@dataclass
class ONNXYoloModelMeta:
    imgsz: Tuple[int, int]
    names: Dict[int, str]

@dataclass
class ONNXYoloResult:
    boxes: np.ndarray
    scores: np.ndarray
    class_ids: np.ndarray
    class_name_mapping: Dict[int, str]
    image: np.ndarray

    def __init__(
            self,
            boxes: np.ndarray,
            scores: np.ndarray,
            class_ids: np.ndarray,
            class_name_mapping: Dict[int, str],
            image: np.ndarray
    ) -> None:
        self.boxes: np.ndarray = boxes
        self.scores: np.ndarray = scores
        self.class_ids: np.ndarray = class_ids
        self.class_name_mapping = class_name_mapping
        self.image: np.ndarray = image

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
            color = (0, 255, 0)
            cv2.rectangle(img, (x, y), (x + w, y + h), color, line_width)
            label = f"{self.class_name_mapping.get(cls, cls)}: {score:.2f}"
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
        self._model_dir, self._model_file = os.path.split(model_path)
        self._model_name = os.path.splitext(self._model_file)[0]
        self._load_model_meta()
        self._engine = ort.InferenceSession(
            model_path,
            providers=['DmlExecutionProvider', 'CPUExecutionProvider']
        )
        self._model_input_name = self._engine.get_inputs()[0].name

    def _load_model_meta(self):
        meta_path = os.path.join(self._model_dir, f"{self._model_name}_meta.json")
        with open(meta_path, "r") as f:
            meta = json.load(f)
        imgsz = json.loads(meta["imgsz"])
        names_mapping = ast.literal_eval(meta["names"])
        self._model_meta = ONNXYoloModelMeta(imgsz, names_mapping)

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

        # 应用NMS
        indices = cv2.dnn.NMSBoxes(boxes, scores, conf_threshold, iou_threshold)

        nms_boxes = np.array([boxes[i] for i in indices])
        nms_scores = np.array([scores[i] for i in indices])
        nms_class_ids = np.array([class_ids[i] for i in indices])
        class_names = np.array([self._model_meta.names.get(cls, cls) for cls in nms_class_ids])
        # print({
        #     "nms_boxes": nms_boxes,
        #     "nms_scores": nms_scores,
        #     "nms_class_ids": nms_class_ids,
        #     "class_names": class_names,
        # })

        return ONNXYoloResult(nms_boxes, nms_scores, nms_class_ids, self._model_meta.names, input_image)

    def __call__(self, img: np.ndarray, conf_threshold: float = 0.7, iou_threshold: float = 0.5) -> ONNXYoloResult:
        input_tensor, ratio, dw, dh = self._preprocess(img)
        outputs = self._engine.run(None, {self._model_input_name: input_tensor})
        return self._postprocess(img, outputs, conf_threshold, iou_threshold, ratio, dw, dh)

class CLIPModelFromONNX:
    session: ort.InferenceSession
    _input_name: str
    _lock: threading.Lock

    def __init__(self, model_path: str=None):
        if not model_path or not os.path.exists(model_path):
            model_path = os.path.join(os.getcwd(), "model", "clip_visual.onnx")
        self.session = ort.InferenceSession(model_path, providers=["DmlExecutionProvider", "CPUExecutionProvider"])
        self._input_name = self.session.get_inputs()[0].name
        self._lock = threading.Lock()

    def preprocess(self, image: np.ndarray) -> np.ndarray:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        image = cv2.resize(image, (224, 224), interpolation=cv2.INTER_CUBIC)
        # 标准化 (mean=[0.48145466, 0.4578275, 0.40821073], std=[0.26862954, 0.26130258, 0.27577711])
        mean = np.array([0.48145466, 0.4578275, 0.40821073]).reshape(1, 1, 3)
        std = np.array([0.26862954, 0.26130258, 0.27577711]).reshape(1, 1, 3)
        image = (image - mean) / std
        image = np.transpose(image, (2, 0, 1))  # [HWC] -> [CHW]
        return image[np.newaxis, :]

    def forward(self, image: np.ndarray) -> np.ndarray:
        input_tensor = self.preprocess(image)
        self._lock.acquire()
        try:
            output = self.session.run(None, {self._input_name: input_tensor})
        except Exception as e:
            logger.error(e)
        finally:
            self._lock.release()
        if output is None:
            return None
        return output[0]  # shape: [1, 512]
