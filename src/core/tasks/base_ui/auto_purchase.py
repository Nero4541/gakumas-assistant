import os.path
from copy import copy
from time import sleep
from typing import TYPE_CHECKING, List, Optional

import cv2
import numpy as np

from src.constants.device.adb import ADBOperation
from src.constants.path.data_path import DataPath
from src.constants.path.debug_path import DebugPath
from src.constants.game.text.button_text import ButtonText
from src.constants.game.text.modal_text import ModalText
from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.core.device.Android.app import Android_App
from src.core.services.clip.item import Item
from src.entity.Game.Components.Button import ButtonList
from src.entity.Game.Components.Modal import Modal
from src.entity.Game.Components.TabBar import TabBar
from src.entity.Game.Page.Types.index import GamePageTypes
from src.models import CLIPMemory
from src.utils.game_database_tools import GakumasDatabase_ItemDataUtils
from src.utils.game_tools import modal_body_extract_item_info
from src.core.inference.ocr_engine import OCRService, OCR_ResultList
from src.utils.opencv_tools import check_color
from src.utils.string_tools import MatchConfig, string_match
from src.utils.logger import logger

if TYPE_CHECKING:
    from src.main import AppProcessor

ocr_service = OCRService()
item_db = GakumasDatabase_ItemDataUtils()

def _exchange_items(app: "AppProcessor", commodity_target: List[str]):
    logger.info(f"Shopping list: {commodity_target}")
    # 上一次获取到的列表哈希
    last_list_hash = None
    not_memory = len(CLIPMemory.select()) == 0
    median_x:Optional[int] = None
    median_y:Optional[int] = None
    while True:
        # 当前页面物品（名）列表
        current_list = []
        item_commodity = app.latest_results.filter_by_labels([BaseUILabels.ITEM,BaseUILabels.CARD_COMMODITY])
        item_commodity_group = item_commodity.find_containing_groups(BaseUILabels.CARD_COMMODITY, [BaseUILabels.ITEM])
        scroll_x, scroll_y = item_commodity.get_COL()
        if median_y is None or median_x is None:
            x_list = [item_group.w - item_group.x for item_group in item_commodity_group]
            y_list = [item_group.h - item_group.y for item_group in item_commodity_group]
            median_x = int(np.median(x_list))
            median_y = int(np.median(y_list))
            logger.debug(f"median_x: {median_x}, median_y: {median_y}")
        # 循环每一个物品
        for index, item_boxe in enumerate(item_commodity_group):
            item = item_boxe.filter_by_label(BaseUILabels.ITEM).first()
            # 跳过过小的框
            if item_boxe.w - item_boxe.x < median_x * 0.8 or item_boxe.h - item_boxe.y < median_y * 0.8:
                logger.warning(f"Skip over small item")
                app.debug_tools.add_box(item.x, item.y, item.w, item.h, label=f"{index} 已跳过：框过小")
                continue
            # 跳过无法交换的物品
            if check_color_result := check_color(item.frame, (0, 0, 85), (179, 90, 145), threshold=40):
                app.debug_tools.add_box(item.x, item.y, item.w, item.h, label=f"{index} 已跳过：无库存\nvalue: {check_color_result.value}", color=(255,255,0))
                logger.debug(f"Skip item {index}(x={item.x},y={item.y}) Reason: 交換済み")
                continue
            # 如果已经在记忆中
            if not not_memory and (clip_result := app.clip_manager.item_clip.retrieve(item.frame, 0.99)):
                logger.debug(f"Item {index}(x={item.x}, y={item.y}) is already in memory, skipping save")
                app.debug_tools.add_box(item.x, item.y, item.w, item.h, label=f"{index} 已获取到存储\n\n物品名：{clip_result.name}", color=(0,255,0))
                # 在购买列表中
                if string_match(clip_result.name, commodity_target, MatchConfig(fuzz_threshold=80)):
                    logger.info(f"purchase {clip_result.name}(index={index}, x={item.x}, y={item.y}) items......")
                    for _ in range(3):
                        app.device.click_element(item_boxe)
                        modal = app.game_utils.wait_for_modal(ModalText.TITLE.EXCHANGE_CONFIRMATION)
                        if modal:
                            app.device.click_element(modal.confirm_button)
                            break
                    app.game_utils.wait_label_exist(BaseUILabels.MODAL_HEADER)
                else:
                    logger.debug(f"{clip_result.name} is not on the shopping list, so skip the purchase.")
                current_list.append(clip_result.name)
            # 不在记忆中
            else:
                logger.debug(f"Item {index} (x={item.x}, y={item.y}) not found in memory, adding to memory.")
                app.debug_tools.add_box(item.x, item.y, item.w, item.h, label=f"{index} 不存在于记忆中", color=(255,0,0))
                # 点击物品
                modal: Optional[Modal] = None
                for _ in range(3):
                    app.device.click_element(item_boxe)
                    sleep(0.5)
                    app.game_utils.wait_loading()
                    modal = app.game_utils.wait_for_modal(ModalText.TITLE.EXCHANGE_CONFIRMATION)
                    if modal:
                        break
                if not modal:
                    sleep(1)
                    continue
                yolo_result_item = copy(item.frame)
                # 截取物品和物品信息
                modal_item_image, item_info = modal_body_extract_item_info(modal.modal_body)
                ocr_results = ocr_service.ocr(item_info)
                ocr_results = OCR_ResultList([res for res in ocr_results if len(res.text) > 2])
                if not ocr_results:
                    logger.warning(f"No OCR results found, skip purchase.")
                    app.device.click_element(modal.cancel_button)
                    continue
                logger.debug(f"OCR_ResultList: {ocr_results}")
                item_name = ocr_results.get_y_min()
                status, result = item_db.search(item_name.text)
                if status:
                    app.clip_manager.item_clip.add_to_memory(modal_item_image, result, 0.99)
                    app.clip_manager.item_clip.add_to_memory(yolo_result_item, result, 0.99)
                    item_name = result.name
                else:
                    logger.warning(f"Item '{item_name}' not found in database after OCR recognition.")
                    os.makedirs(DebugPath.UnknownItem, exist_ok=True)
                    cv2.imwrite(os.path.join(DebugPath.UnknownItem, f"item_info_{index}.png"), item_info)
                    cv2.imwrite(os.path.join(DebugPath.UnknownItem, f"modal_item_image_{index}.png"), modal_item_image)
                    cv2.imwrite(os.path.join(DebugPath.UnknownItem, f"modal_body_image_{index}.png"), modal.modal_body)
                current_list.append(item_name)
                # 在购买列表的情况下购买
                if string_match(item_name, commodity_target, MatchConfig(fuzz_threshold=80)):
                    logger.info(f"purchase {item_name}(index={index}, x={item.x}, y={item.y}) items......")
                    app.device.click_element(modal.confirm_button)
                else:
                    logger.debug(f"{item_name} is not on the shopping list, so skip the purchase.")
                    app.device.click_element(modal.cancel_button)
                app.game_utils.wait_label_exist(BaseUILabels.MODAL_HEADER)
                app.debug_tools.show()
                sleep(0.5)
        # sleep(5)
        # 如果历史哈希不相同，则向下滚动
        app.debug_tools.clear_all()
        if last_list_hash != hash(frozenset(current_list)):
            last_list_hash = hash(frozenset(current_list))
            app.device.scrollY(scroll_x, scroll_y, -5)
            app.game_utils.wait_frame_stable()
        else:
            break


def action__receive_weekly_gift(app: "AppProcessor"):
    """领取每周礼包"""
    app.game_utils.click_button(ButtonText.SHOP.PACK, match_config=MatchConfig(use_fuzz=False))
    app.game_utils.update_current_location(GamePageTypes.HOME_TAB.SHOP_SUB_PAGE.PACK)
    sleep(3)
    height, width = app.latest_frame.shape[:2]
    for _ in range(3):
        buttons = ButtonList(app.latest_results)
        for button in buttons:
            if ButtonText.FREE in button.text and button.is_disabled() is False:
                while True:
                    if not app.latest_results.exists_label(BaseUILabels.MODAL_HEADER):
                        app.device.click_element(button)
                    sleep(0.5)
                    if not app.latest_results.exists_label(BaseUILabels.MODAL_HEADER):
                        continue
                    app.game_utils.click_button(ButtonText.CONFIRM, match_config=MatchConfig(fuzz_threshold=90))
                    sleep(0.5)
                    app.game_utils.click_button(ButtonText.CLOSE, match_config=MatchConfig(fuzz_threshold=90))
                    break
        app.device.scrollY(width // 2, height // 2, -20)
        app.game_utils.wait_frame_stable()
    app.game_utils.back_next_page()
    app.game_utils.wait_loading()
    app.game_utils.update_current_location(GamePageTypes.HOME_TAB.SHOP)

def action__daily_exchange(app: "AppProcessor"):
    app.game_utils.click_button(ButtonText.SHOP.DAILY_EXCHANGE, match_config=MatchConfig(fuzz_threshold=90))
    app.game_utils.wait_location_update(GamePageTypes.HOME_TAB.SHOP_SUB_PAGE.DAILY_EXCHANGE)
    tabbar: Optional[TabBar] = None
    for _ in range(3):
        app.game_utils.wait_for_label(BaseUILabels.TAB_BAR)
        tabbar = TabBar(app.latest_results.filter_by_label(BaseUILabels.TAB_BAR).first())
        if tabbar:
            break
    if not tabbar:
        return False
    commodity_target = []
    for item_id in app.config_service().task__auto_purchase.daily_buy_list.value:
        if (result := item_db.get_by_id(item_id)) is not None:
            commodity_target.append(result.name)
    for tab_item in tabbar:
        app.device.click_element(tab_item)
        app.game_utils.wait_frame_stable()
        _exchange_items(app, commodity_target)

    return True