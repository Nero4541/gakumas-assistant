from typing import Tuple

import cv2
import numpy as np

from src.constants import *
from src.entity.Game.Components.Button import Button
from src.entity.Game.Components.Modal import Modal
from src.entity.Yolo import Yolo_Box, Yolo_Results
from src.utils.ocr_instance import OCRService
from src.utils.logger import logger
from src.utils.opencv_tools import gen_color_mask


@logger.catch
def get_modal(yolo_result: Yolo_Results, frame: np.array, no_body: bool = False) -> Modal | None:
    """
    获取模态框
    :param no_body: 不识别模态框主体（加速）
    :param yolo_result: yolo 识别结果
    :param frame: 图像帧
    :return: 解析后的 Modal 对象
    """
    # try:
    # 获取模态框头部
    if not yolo_result.exists_all_labels([base_labels.modal_header, base_labels.button]):
        logger.warning("模态框不完整")
        return None
    modal = yolo_result.filter_by_labels([base_labels.modal_header, base_labels.button])
    modal_header = modal.filter_by_label(base_labels.modal_header).first()
    # modal_header.frame = gen_color_mask(modal_header.frame, (0,0,230), (0,0,255))
    # _, modal_header.frame = cv2.threshold(modal_header.frame, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ocr_service = OCRService()
    modal_header_ocr_result = ocr_service.ocr(modal_header.frame)
    modal_header_ocr_result.auto_merge_lines()
    modal_header_text = modal_header_ocr_result.first().text
    # 获取确认和取消按钮
    buttons = modal.filter_by_label(base_labels.button).group_yolo_boxes_by_position(30, None)
    if buttons:
        buttons = buttons.pop()
        confirm_button = buttons.get_x_max_element()
        cancel_button = buttons.get_x_min_element()
    else:
        # 不区分按钮类型时，取最下面的按钮作为取消按钮
        buttons = modal.filter_by_label(base_labels.button).get_y_max_element()
        confirm_button = None
        cancel_button = buttons
    if not confirm_button and not cancel_button:
        logger.warning("Cancel or Confirm buttons not found")
        return None
    confirm_button = Button(confirm_button.first()) if confirm_button else None
    cancel_button = Button(cancel_button.first()) if cancel_button else None
    # 计算模态框主体区域
    if confirm_button and cancel_button:
        modal_body_y = max(cancel_button.y, confirm_button.y)
    else:
        modal_body_y = confirm_button.y if confirm_button else cancel_button.y
    modal_body_frame = frame[modal_header.h:modal_body_y, modal_header.x:modal_header.w]
    modal_body_text = "" if no_body else " ".join([item.text for item in ocr_service.ocr(modal_body_frame)])
    return Modal(modal_header_text, modal_body_frame, modal_body_text, confirm_button, cancel_button)