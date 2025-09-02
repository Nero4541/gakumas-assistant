# import ast
# import os
# import json
# from dataclasses import dataclass
# from typing import List, Tuple, Generator, Optional, Union
#
# import numpy as np
# import cv2
# import onnxruntime as ort
import os

import cv2

# model_path = "../model/base_ui.onnx"

# engine: ort.InferenceSession = ort.InferenceSession(
#     model_path,
#     providers=['CUDAExecutionProvider', 'DmlExecutionProvider', 'CPUExecutionProvider']
# )
#
# def _load_model_mata(model_path):
#     model_dir, model_file = os.path.split(model_path)
#     model_name = os.path.splitext(model_file)[0]
#     meta_path = os.path.join(model_dir, f"{model_name}_meta.json")
#
#     with open(meta_path, "r") as f:
#         meta = json.load(f)
#
#     return meta
#
# meta = _load_model_mata(model_path)
# print(meta)
# names_mapping = ast.literal_eval(meta["names"])
# img_input_size = 640
# img = cv2.imread("main_memu__tabbar2.png")

# def preprocess(img: np.ndarray):
#     """
#     图像预处理
#     :param img: 图像
#     :return:
#     """
#     img_resized = cv2.resize(img, (img_input_size, img_input_size))
#     img_resized = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
#     img_resized = img_resized.transpose(2, 0, 1).astype(np.float32) / 255.0
#     return np.expand_dims(img_resized, axis=0)
#
# input_tensor = preprocess(img)
# outputs = engine.run(None, {"images": input_tensor})
# print(outputs)
#
# def postprocess(input_image: np.ndarray, results: np.ndarray, conf_threshold:float=0.7, iou_threshold:float=0.5):
#     """
#
#     :param input_image:
#     :param results:
#     :param conf_threshold:
#     :param iou_threshold:
#     :return:
#     """
#     # 转置并压缩输出以匹配期望的形状：(8400, 84)
#     outputs = np.transpose(np.squeeze(results[0]))
#     # 获取输出数组的行数
#     rows = outputs.shape[0]
#     # 存储检测到的边界框、分数和类别ID的列表
#     boxes = []
#     scores = []
#     class_ids = []
#     # 计算边界框坐标的比例因子
#     w, h, _ = input_image.shape
#     x_factor = img_input_size / w
#     y_factor = img_input_size / h
#
#     # 遍历输出数组的每一行
#     for i in range(rows):
#         # 从当前行提取类别的得分
#         classes_scores = outputs[i][4:]
#         # 找到类别得分中的最大值
#         max_score = np.amax(classes_scores)
#
#         # 如果最大得分大于或等于置信度阈值
#         if max_score >= conf_threshold:
#             # 获取得分最高的类别ID
#             class_id = np.argmax(classes_scores)
#
#             # 从当前行提取边界框坐标
#             x, y, w, h = outputs[i][0], outputs[i][1], outputs[i][2], outputs[i][3]
#
#             # 计算边界框的缩放坐标
#             left = int((x - w / 2) * x_factor)
#             top = int((y - h / 2) * y_factor)
#             width = int(w * x_factor)
#             height = int(h * y_factor)
#
#             # 将类别ID、得分和边界框坐标添加到相应的列表中
#             class_ids.append(class_id)
#             scores.append(max_score)
#             boxes.append([left, top, width, height])
#
#     # 应用非极大抑制以过滤重叠的边界框
#     indices = cv2.dnn.NMSBoxes(boxes, scores, conf_threshold, iou_threshold)
#
#     output_results = []
#
#     # 遍历非极大抑制后选择的索引
#     for i in indices:
#         # 获取与索引对应的边界框、得分和类别ID
#         box = boxes[i]
#         score = scores[i]
#         class_id = class_ids[i]
#         # 在输入图像上绘制检测结果
#         # self.draw_detections(input_image, box, score, class_id)
#         output_results.append({
#             "box": box,
#             "score": score,
#             "label": names_mapping[class_id],
#         })
#     # 返回修改后的输入图像
#     return output_results
#
#
# # def postprocess(outputs: List[np.ndarray], conf_threshold: float):
# #     output = outputs[0][0]
# #     boxes, scores, class_ids = [], [], []
# #
# #     for pred in output:
# #         conf = pred[4]
# #         class_confidences = pred[5:]
# #         class_id = int(np.argmax(class_confidences))
# #         class_score = class_confidences[class_id]
# #         score = conf * class_score
# #         if score < conf_threshold:
# #             continue
# #         boxes.append(pred[:4])
# #         scores.append(score)
# #         class_ids.append(names_mapping.get(class_id, class_id))
# #
# #     return {
# #         "boxes": boxes,
# #         "scores": scores,
# #         "class_ids": class_ids
# #     }
#
# predictions = postprocess(img, outputs, 0.7)
# print(predictions)

# from src.core.ONNX import YoloModelFromONNX
# from src.entity.Yolo import Yolo_Results
#
# YoloModel = YoloModelFromONNX(model_path)
# res = YoloModel(img)
# print(res)
# cv2.imshow('image', img)
# cv2.imshow('plot', res.plot())
# print(Yolo_Results(res))
#
# cv2.waitKey(0)

from src.core.inference.ONNX import CLIPModelFromONNX
clip = CLIPModelFromONNX("../model/clip_visual.onnx")
base_path = os.path.join(os.getcwd(), "button_disabled_test")
for filename in os.listdir(base_path):
    if filename.endswith(".png"):
        img = cv2.imread(os.path.join(base_path, filename))
        result = clip.forward(img)
        print(result)