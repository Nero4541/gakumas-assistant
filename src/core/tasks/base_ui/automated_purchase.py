from copy import copy
from time import sleep

from src.constants import *
from typing import TYPE_CHECKING, List

from src.core.CLIP_services.item import ItemInfo
from src.entity.Game.Components.Button import ButtonList
from src.entity.Game.Components.TabBar import TabBar
from src.entity.Game.Page.Types.index import GamePageTypes
from src.utils.game_tools import modal_body_extract_item_info
from src.utils.ocr_instance import OCRService, OCR_ResultList
from src.utils.string_tools import MatchConfig, string_match
from src.utils.logger import logger

if TYPE_CHECKING:
    from src.main import AppProcessor

ocr_service = OCRService()

def _exchange_items(app: "AppProcessor", commodity_target: List[str]):
    logger.info(f"Shopping list: {commodity_target}")
    # 上一次获取到的列表哈希
    last_list_hash = None
    while True:
        # 当前页面物品（名）列表
        current_list = []
        item_commodity = app.latest_results.filter_by_labels([base_labels.item,base_labels.card__commodity])
        item_commodity_group = item_commodity.find_containing_groups(base_labels.card__commodity, [base_labels.item])
        scroll_x, scroll_y = item_commodity.get_COL()
        # 循环每一个物品
        for index, item_boxe in enumerate(item_commodity_group):
            item = item_boxe.filter_by_label(base_labels.item).first()
            # 跳过无法交换的物品
            if ocr_service.ocr(item.frame).search("交換済み"):
                logger.debug(f"Skip item {index}(x={item.x},y={item.y}) Reason: 交換済み")
                continue
            # 如果已经在记忆中
            if clip_result := app.clip_manager.item_clip.retrieve(item.frame, 0.99):
                logger.debug(f"Item {index}(x={item.x}, y={item.y}) is already in memory, skipping save")
                # 在购买列表中
                if string_match(clip_result.name, commodity_target, MatchConfig(fuzz_threshold=80)):
                    logger.info(f"purchase {clip_result.name}(index={index}, x={item.x}, y={item.y}) items......")
                    app.app.click_element(item_boxe)
                    modal = app.game_utils.wait_for_modal(modal_text.exchange_confirmation)
                    app.app.click_element(modal.confirm_button)
                else:
                    logger.debug(f"{clip_result.name} is not on the shopping list, so skip the purchase.")
                current_list.append(clip_result.name)
            # 不在记忆中
            else:
                logger.debug(f"Item {index} (x={item.x}, y={item.y}) not found in memory, adding to memory.")
                # 点击物品
                app.app.click_element(item_boxe)
                modal = app.game_utils.wait_for_modal(modal_text.exchange_confirmation)
                yolo_result_item = copy(item.frame)
                # 截取物品和物品信息
                modal_item_image, item_info = modal_body_extract_item_info(modal.modal_body)
                ocr_results = ocr_service.ocr(item_info)
                logger.debug(ocr_results)
                ocr_results = OCR_ResultList([res for res in ocr_results if len(res.text) > 2])
                item_name = ocr_results.get_y_min()
                item_info = ocr_results.exclude([item_name])
                item_name = item_name.text
                item_info = ItemInfo(item_name, [_.text for _ in item_info])
                # 添加到记忆中
                app.clip_manager.item_clip.add_to_memory(modal_item_image, item_info, 0.99)
                app.clip_manager.item_clip.add_to_memory(yolo_result_item, item_info, 0.99)
                current_list.append(item_name)
                # 在购买列表的情况下购买
                if string_match(item_name, commodity_target, MatchConfig(fuzz_threshold=80)):
                    logger.info(f"purchase {item_name}(index={index}, x={item.x}, y={item.y}) items......")
                    app.app.click_element(modal.confirm_button)
                else:
                    logger.debug(f"{item_name} is not on the shopping list, so skip the purchase.")
                    app.app.click_element(modal.cancel_button)
                sleep(0.5)
        # 如果历史哈希不相同，则向下滚动
        if last_list_hash != hash(frozenset(current_list)):  # 使用哈希值进行比较
            logger.debug(current_list)
            last_list_hash = hash(frozenset(current_list))
            app.app.scrollY(scroll_x,scroll_y,-5)
        else:
            break


def action__receive_weekly_gift(app: "AppProcessor"):
    """领取每周礼包"""
    app.game_utils.click_button("パック", match_config=MatchConfig(use_fuzz=False))
    app.game_utils.update_current_location(GamePageTypes.HOME_TAB.SHOP_SUB_PAGE.PACK)
    sleep(3)
    height, width = app.latest_frame.shape[:2]
    for _ in range(3):
        buttons = ButtonList(app.latest_results)
        for button in buttons:
            if "無料" in button.text and button.is_disabled() is False:
                app.app.click_element(button)
                sleep(0.5)
                app.game_utils.click_button("決定")
                sleep(0.5)
                app.game_utils.click_button("閉じる")
        app.app.scrollY(width//2, height//2, -20)
    app.game_utils.back_next_page()
    app.game_utils.wait_loading()
    app.game_utils.update_current_location(GamePageTypes.HOME_TAB.SHOP)

def action__daily_exchange(app: "AppProcessor", commodity_target: List[str]):
    app.game_utils.click_button("デイリー交換所")
    app.game_utils.wait_location_update(GamePageTypes.HOME_TAB.SHOP_SUB_PAGE.DAILY_EXCHANGE)
    tabbar = TabBar(app.latest_results.filter_by_label(base_labels.tab_bar).first())
    for tab_item in tabbar:
        app.app.click_element(tab_item)
        sleep(2)
        _exchange_items(app, commodity_target)