from copy import copy

import cv2
import numpy as np

from src.constants.location import Location
from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.entity.Game.Components.Button import Button
from src.entity.Game.Components.Modal import Modal

from src.entity.Yolo import Yolo_Results
from src.entity.Game.Page.Types.index import GamePageTypes
from src.utils.logger import logger
from src.core.inference.ocr_engine import OCRService
from src.utils.opencv_tools import check_status_detection, get_mask_contours, extract_roi_from_mask, check_color, \
    filter_by_rectangle_shape, get_max_contour
from src.utils.performance_tools import timeit
from src.utils.string_tools import string_match, MatchConfig

ocr_service = OCRService()

@timeit
def get_current_location(boxes: Yolo_Results) -> str | None:
    if boxes.exists_label(BaseUILabels.START_MENU_LOGO):
        return GamePageTypes.START_GAME
    if boxes.exists_label(BaseUILabels.GENERAL_LOADING1) or boxes.exists_label(
            BaseUILabels.GENERAL_LOADING2):
        return GamePageTypes.LOADING
    # 映射标签 → 页面类型
    TAB_LABEL_TO_PAGE = {
        BaseUILabels.TAB_COMMUNICATE: GamePageTypes.MAIN_MENU__COMMUNICATE,
        BaseUILabels.TAB_IDOL: GamePageTypes.MAIN_MENU__IDOL,
        BaseUILabels.TAB_HOME: GamePageTypes.MAIN_MENU__HOME,
        BaseUILabels.TAB_GACHA: GamePageTypes.MAIN_MENU__GACHA,
        BaseUILabels.TAB_CONTEST: GamePageTypes.MAIN_MENU__CONTEST,
        Location.MAIN_UI.Page.PRESENT: GamePageTypes.HOME_TAB.GIFT,
        Location.MAIN_UI.Page.DAILY_TASK: GamePageTypes.HOME_TAB.TASK,
        Location.MAIN_UI.Page.ACHIEVEMENT: GamePageTypes.HOME_TAB.ACHIEVEMENT,
        Location.MAIN_UI.Page.ACHIEVEMENT_IDOL: GamePageTypes.HOME_TAB.ACHIEVEMENT_SUB_PAGE.IDOL,
        Location.MAIN_UI.Page.ACHIEVEMENT_PRODUCER: GamePageTypes.HOME_TAB.ACHIEVEMENT_SUB_PAGE.PRODUCER,
        Location.MAIN_UI.Page.ACHIEVEMENT_OTHER: GamePageTypes.HOME_TAB.ACHIEVEMENT_SUB_PAGE.OTHER,
        Location.MAIN_UI.Page.PLAN: GamePageTypes.HOME_TAB.PASS_REWARD,
        Location.MAIN_UI.Page.DISPATCH_WORK: GamePageTypes.HOME_TAB.WORK,
        Location.MAIN_UI.Page.SHOP: GamePageTypes.HOME_TAB.SHOP,
        Location.MAIN_UI.Page.SHOP_GEM: GamePageTypes.HOME_TAB.SHOP_SUB_PAGE.GEM,
        Location.MAIN_UI.Page.SHOP_PACK: GamePageTypes.HOME_TAB.SHOP_SUB_PAGE.PACK,
        Location.MAIN_UI.Page.SHOP_PASS: GamePageTypes.HOME_TAB.SHOP_SUB_PAGE.PASS,
        Location.MAIN_UI.Page.SHOP_COIN_GACHA: GamePageTypes.HOME_TAB.SHOP_SUB_PAGE.COIN_GACHA,
        Location.MAIN_UI.Page.SHOP_DAILY_EXCHANGE: GamePageTypes.HOME_TAB.SHOP_SUB_PAGE.DAILY_EXCHANGE,
        Location.MAIN_UI.Page.SHOP_COSTUME_EXCHANGE: GamePageTypes.HOME_TAB.SHOP_SUB_PAGE.COSTUME_EXCHANGE,
        Location.MAIN_UI.Page.SHOP_ITEM_EXCHANGE: GamePageTypes.HOME_TAB.SHOP_SUB_PAGE.ITEM_EXCHANGE,
        Location.MAIN_UI.Page.SHOP_TICKET_EXCHANGE: GamePageTypes.HOME_TAB.SHOP_SUB_PAGE.TICKET_EXCHANGE,
        Location.MAIN_UI.Page.CONTEST: GamePageTypes.CONTEST_TAB.ARENA,
        Location.MAIN_UI.Page.THE_ROAD_TO_IDOLS: GamePageTypes.CONTEST_TAB.THE_ROAD_TO_IDOL,
        Location.MAIN_UI.Page.HATSUSEI_COMMUNITY: GamePageTypes.Communicate_TAB.MAIN_STORY,
        Location.MAIN_UI.Page.IDOL_COMMUNITY: GamePageTypes.Communicate_TAB.BOND_STORIES,
        Location.MAIN_UI.Page.PRODUCE_CARD_LIST: GamePageTypes.Communicate_TAB.SUPPORT_CARD_ARCHIVE,
        Location.MAIN_UI.Page.EVENT_PLOT: GamePageTypes.Communicate_TAB.PAST_EVENTS,
        Location.MAIN_UI.Page.PRODUCER_ILLUSTRATED: GamePageTypes.SUB_MENU.PRODUCER_ILLUSTRATED,
    }
    MAIN_UI_TABS = list(TAB_LABEL_TO_PAGE.keys())[:5]
    if boxes.exists_all_labels(MAIN_UI_TABS):
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
    elif current_location := boxes.filter_by_label(BaseUILabels.CURRENT_LOCATION):
        current_location = current_location.first()
        if current_location.frame is None or current_location.frame.size == 0:
            logger.debug("Not current location frame")
            return GamePageTypes.UNKNOWN
        ocr_result = ocr_service.ocr(current_location.frame)
        if ocr_result is None:
            logger.debug("Current location not text")
            return GamePageTypes.UNKNOWN
        location_text = "".join([ocr_item.text for ocr_item in ocr_result])
        match_result = string_match(location_text, list(TAB_LABEL_TO_PAGE.keys()), MatchConfig(fuzz_threshold=90))
        if not match_result:
            return GamePageTypes.UNKNOWN
        return TAB_LABEL_TO_PAGE.get(match_result.result)
    return GamePageTypes.UNKNOWN

@timeit
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

@timeit
def modal_body_extract_item_info(
        img,
        item_lower: tuple[int, int, int] = (0,0,0),
        item_upper: tuple[int, int, int] = (179,90,120),
        mark_lower: tuple[int, int, int] = (90,85,230),
        mark_upper: tuple[int, int, int] = (98,145,250)
):
    """
    在模态框中提取物品信息
    :param img: 图像
    :param item_lower: 物品外框下值
    :param item_upper: 物品外框上值
    :param mark_lower: 锚点下值
    :param mark_upper: 锚点上值
    :return: bool
    """
    # 取出物品
    item_contours = get_mask_contours(img, item_lower, item_upper, iterations=2)
    item_contours = filter_by_rectangle_shape(item_contours, 50)
    if item_contours is None:
        return None, None
    item_x,item_y,item_w,item_h = cv2.boundingRect(get_max_contour(item_contours))
    item = img[item_y:item_y+item_h, item_x:item_x+item_w]
    # 取出物品信息锚点
    mark_y = 0
    contours = get_mask_contours(img[item_y+item_h:], mark_lower, mark_upper)
    for contour in contours:
        _x,_y,_w,_h = cv2.boundingRect(contour)
        if mark_y == 0:
            mark_y = _y
            continue
        if _h > 5 and _w > 5:
            mark_y = min(_y, mark_y)
    mark_y = item_y+item_h+mark_y
    if mark_y < item_y + item_h and not check_color(img[item_y+item_h:item_y+item_h+20, item_x+item_w:], (0,0,45), (0,0,108), threshold=5):
        item_info = img[item_y-10:item_y+item_h, item_x+item_w:]
    else:
        item_info = img[item_y-10:mark_y, item_x+item_w:]

    return item, item_info

@timeit
def get_modal(yolo_result: Yolo_Results, no_body: bool = False) -> Modal | None:
    """
    获取模态框
    :param yolo_result: yolo结果集
    :param no_body: 不识别模态框主体（加速）
    :return: 解析后的 Modal 对象
    """
    if not yolo_result.exists_all_labels([BaseUILabels.MODAL_HEADER, BaseUILabels.BUTTON]):
        logger.warning("模态框不完整")
        return None
    yolo_result = copy(yolo_result)
    modal = yolo_result.filter_by_labels([BaseUILabels.MODAL_HEADER, BaseUILabels.BUTTON])
    modal_header = modal.filter_by_label(BaseUILabels.MODAL_HEADER).first()
    # 获取 header 内按钮的最小 x
    buttons_in_header = [
        btn.x for btn in modal.filter_by_labels([BaseUILabels.BUTTON])
        if modal_header.x < btn.cx < modal_header.w and
           modal_header.y < btn.cy < modal_header.h
    ]
    modal_button_min_x = min(buttons_in_header, default=modal_header.w)

    # OCR 模态框头部（排除按钮部分）
    modal_header_ocr_result = ocr_service.ocr(
        modal_header.frame[:, :modal_button_min_x]
    )
    modal_header_ocr_result.auto_merge_lines()
    modal_header_text = modal_header_ocr_result.first().text
    # 在结果集中排除模态框头部按钮
    modal = modal.remove_by_yolo_boxes(buttons_in_header)
    # 获取确认和取消按钮
    buttons = modal.filter_by_label(BaseUILabels.BUTTON).group_yolo_boxes_by_position(30, None)
    if buttons:
        buttons = buttons.pop()
        confirm_button = buttons.get_x_max_element()
        cancel_button = buttons.get_x_min_element()
    else:
        # 不区分按钮类型时，取最下面的按钮作为取消按钮
        buttons = modal.filter_by_label(BaseUILabels.BUTTON).get_y_max_element()
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
    modal_body_frame = yolo_result.frame[modal_header.h:modal_body_y, modal_header.x:modal_header.w]
    modal_body_text = None if no_body else " ".join([item.text for item in ocr_service.ocr(modal_body_frame)])
    return Modal(
        modal_header_text,
        modal_body_frame,
        modal_body_text,
        confirm_button,
        cancel_button
    )
