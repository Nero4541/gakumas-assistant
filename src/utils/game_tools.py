from typing import List

import cv2
import numpy as np
from loguru import logger

from src.constants.base_ui import labels
from src.entity.Game.Components.Button import Button
from src.entity.Game.Components.Modal import Modal

from src.entity.Yolo import Yolo_Results, Yolo_Box
from src.constants import *
from src.entity.Game.Page.Types.index import GamePageTypes
from src.utils.logger import logger
from src.utils.ocr_instance import OCRService
from src.utils.opencv_tools import check_status_detection, get_mask_contours, extract_roi_from_mask


@logger.catch
def get_current_location(boxes: Yolo_Results) -> str | None:
    if boxes.exists_label(base_labels.start_menu_logo):
        return GamePageTypes.START_GAME
    if boxes.exists_label(base_labels.general_loading1) or boxes.exists_label(
        base_labels.general_loading2):
        return GamePageTypes.LOADING
    # 映射标签 → 页面类型
    TAB_LABEL_TO_PAGE = {
        base_labels.tab_communicate: GamePageTypes.MAIN_MENU__COMMUNICATE,
        base_labels.tab_idol: GamePageTypes.MAIN_MENU__IDOL,
        base_labels.tab_home: GamePageTypes.MAIN_MENU__HOME,
        base_labels.tab_gacha: GamePageTypes.MAIN_MENU__GACHA,
        base_labels.tab_contest: GamePageTypes.MAIN_MENU__CONTEST,
        location.page__present: GamePageTypes.HOME_TAB.GIFT,
        location.page__daily_task: GamePageTypes.HOME_TAB.TASK,
        location.page__achievement: GamePageTypes.HOME_TAB.ACHIEVEMENT,
        location.page__achievement_idol: GamePageTypes.HOME_TAB.ACHIEVEMENT_SUB_PAGR.IDOL,
        location.page__achievement_producer: GamePageTypes.HOME_TAB.ACHIEVEMENT_SUB_PAGR.PRODUCER,
        location.page__achievement_other: GamePageTypes.HOME_TAB.ACHIEVEMENT_SUB_PAGR.OTHER,
        location.page__plan: GamePageTypes.HOME_TAB.MISSION_PASS,
        location.page__dispatch_work: GamePageTypes.HOME_TAB.WORK,
        location.page__shop: GamePageTypes.HOME_TAB.SHOP,
        location.page__shop_gem: GamePageTypes.HOME_TAB.SHOP_SUB_PAGE.GEM,
        location.page__shop_pack: GamePageTypes.HOME_TAB.SHOP_SUB_PAGE.PACK,
        location.page__shop_pass: GamePageTypes.HOME_TAB.SHOP_SUB_PAGE.PASS,
        location.page__shop_coin_gacha: GamePageTypes.HOME_TAB.SHOP_SUB_PAGE.COIN_GACHA,
        location.page__shop_daily_exchange: GamePageTypes.HOME_TAB.SHOP_SUB_PAGE.DAILY_EXCHANGE,
        location.page__shop_costume_exchange: GamePageTypes.HOME_TAB.SHOP_SUB_PAGE.COSTUME_EXCHANGE,
        location.page__shop_item_exchange: GamePageTypes.HOME_TAB.SHOP_SUB_PAGE.ITEM_EXCHANGE,
        location.page__shop_ticket_exchange: GamePageTypes.HOME_TAB.SHOP_SUB_PAGE.TICKET_EXCHANGE,
        location.page__contest: GamePageTypes.CONTEST_TAB.ARENA,
        location.page__the_road_to_idols: GamePageTypes.CONTEST_TAB.THE_ROAD_TO_IDOL,
        location.page__hatsusei_community: GamePageTypes.Communicate_TAB.MAIN_STORY,
        location.page__idol_community: GamePageTypes.Communicate_TAB.BOND_STORIES,
        location.page__produce_card_list: GamePageTypes.Communicate_TAB.SUPPORT_CARD_ARCHIVE,
        location.page__event_plot: GamePageTypes.Communicate_TAB.PAST_EVENTS,
        location.page__producer_illustrated: GamePageTypes.SUB_MENU.PRODUCER_ILLUSTRATED,
    }
    MAIN_UI_TABS = list(TAB_LABEL_TO_PAGE.keys())[:5]
    if boxes.exists_all_labels(MAIN_UI_TABS):
        # logger.debug("Main UI mode")
        home_tab_bar = boxes.filter_by_labels(MAIN_UI_TABS)
        for item in home_tab_bar:
            if check_status_detection(
                item.frame,
                upper_color=(13,215,255),
                lower_color=(5,149,205),
                background_upper_color=(30,115,255),
                background_lower_color=(0,35,225)
            ):
                return TAB_LABEL_TO_PAGE.get(item.label)
    elif boxes.exists_label(base_labels.current_location):
        # logger.debug("Current location mode")
        current_location = boxes.filter_by_label(base_labels.current_location).first()
        if current_location.frame is None or current_location.frame.size == 0:
            logger.debug("Not current location frame")
            return GamePageTypes.UNKNOWN
        ocr_service = OCRService()
        ocr_result = ocr_service.ocr(current_location.frame)
        if ocr_result is None:
            logger.debug("Current location not text")
            return GamePageTypes.UNKNOWN
        location_text = "".join([ocr_item.text for ocr_item in ocr_result])
        logger.debug(location_text)
        for label in TAB_LABEL_TO_PAGE.keys():
            if label in location_text:
                return TAB_LABEL_TO_PAGE.get(label)
    return GamePageTypes.UNKNOWN

def extract_skill_card_and_info(img):
    """提取技能卡和技能卡信息，仅【P图鉴】页面可用"""
    img_w, img_h = img.shape[:2]

    # 提取信息边框的轮廓
    lower_color = np.array([0, 0, 180])
    upper_color = np.array([0, 0, 220])
    contours = get_mask_contours(img, lower_color, upper_color)

    # 技能卡边框颜色范围
    skill_card_lower_color = np.array([104, 32, 87])
    skill_card_upper_color = np.array([115, 87, 142])

    # 提取每个区域
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)

        # 筛选条件：宽度必须大于图像宽度的一半，且高度大于图像高度的四分之一
        if w > img_w // 2 and h > img_h // 4:
            roi = img[y:y + h, x:x + w]

            # 提取技能卡区域的轮廓
            skill_card_contours = get_mask_contours(roi, skill_card_lower_color, skill_card_upper_color)

            # 找到技能卡最大宽度并提取
            for skill_card_cnt in skill_card_contours:
                x_skill, y_skill, w_skill, h_skill = cv2.boundingRect(skill_card_cnt)
                if h_skill >= h // 3:
                    skill_card = roi[y_skill:y_skill + h_skill, x_skill:x_skill + w_skill]

                    # 提取技能卡信息区域
                    skill_card_info = roi[:, x_skill + w_skill:]
                    skill_card_info = cv2.cvtColor(skill_card_info, cv2.COLOR_BGR2GRAY)
                    _, skill_card_info = cv2.threshold(skill_card_info, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

                    # 返回技能卡和信息区域
                    return roi, skill_card, skill_card_info
    return None, None, None  # 如果没有找到符合条件的区域

def modal_body_extract_item_info(img):
    """
    在模态框中提取物品信息
    :param img:
    :return:
    """
    item_lower = np.array([88,10,95])
    item_upper = np.array([108,19,108])

    mark_lower = np.array([96,75,231])
    mark_upper = np.array([98,145,250])

    item_marks = extract_roi_from_mask(img, item_lower, item_upper)

    if not item_marks:
        return None, None

    item_x,item_y,item_w,item_h = item_marks

    item = img[item_y:item_y+item_h, item_x:item_x+item_w]

    mark_y = 0
    contours = get_mask_contours(img[item_y+item_h:], mark_lower, mark_upper)
    for contour in contours:
        _x,_y,_w,_h = cv2.boundingRect(contour)
        if _h > 5 and _w > 5:
            mark_y = min(_y, mark_y)
    mark_y = item_y+item_h+mark_y
    if mark_y < item_y + item_h:
        item_info = img[item_y-10:item_y+item_h, item_x+item_w:]
    else:
        item_info = img[item_y-10:mark_y, item_x+item_w:]

    return item, item_info


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
