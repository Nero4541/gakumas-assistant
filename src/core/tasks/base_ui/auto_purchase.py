import os.path
import re
from copy import copy
from time import sleep
from typing import TYPE_CHECKING, List, Optional, Tuple

import cv2
import numpy as np

from src.constants.device.adb import ADBOperation
from src.constants.game.text.general_text import GeneralText
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
from src.entity.Yolo import Yolo_Box, Yolo_Results
from src.models import CLIPMemory
from src.utils.game_database_tools import GakumasDatabase_ItemDataUtils
from src.utils.game_tools import modal_body_extract_item_info
from src.core.inference.ocr_engine import OCRService, OCR_ResultList
from src.utils.opencv_tools import check_color, check_frame_change
from src.utils.string_tools import MatchConfig, string_match
from src.utils.logger import logger

if TYPE_CHECKING:
    from src.main import AppProcessor

ocr_service = OCRService()
item_db = GakumasDatabase_ItemDataUtils()

def _calculate_median_size(item_groups: List) -> Tuple[int, int]:
    """计算当前页面物品框的中位数宽高，用于过滤误识别"""
    if not item_groups:
        return 0, 0
    x_list = [g.w - g.x for g in item_groups]
    y_list = [g.h - g.y for g in item_groups]
    return int(np.median(x_list)), int(np.median(y_list))

def _is_valid_item(app, item_box, item_inner, median_x, median_y, index) -> bool:
    """检查物品是否有效（尺寸检查 + 颜色检查）"""
    # 1. 尺寸检查
    if median_x > 0 and median_y > 0:
        if item_box.w - item_box.x < median_x * 0.8 or item_box.h - item_box.y < median_y * 0.8:
            logger.warning(f"Skip over small item {index}")
            app.debug_tools.add_box(
                item_inner.x,
                item_inner.y,
                item_inner.w,
                item_inner.h,
                label=f"{index} 已跳过：框过小"
            )
            return False

    # 2. 颜色检查 (是否已兑换/不可用)
    if check_color_result := check_color(item_inner.frame, (0, 0, 85), (179, 90, 145), threshold=40):
        logger.debug(f"Skip item {index} Reason: 交換済み/无库存")
        app.debug_tools.add_box(
            item_inner.x,
            item_inner.y,
            item_inner.w,
            item_inner.h,
            label=f"{index} 已跳过：无库存\nval: {check_color_result.value}",
            color=(255, 255, 0)
        )
        return False

    return True

def _handle_known_item(app, item_inner, clip_result, commodity_target, index):
    """处理已经在记忆中的物品"""
    logger.debug(f"Item {index} found in memory: {clip_result.name}")
    app.debug_tools.add_box(
        item_inner.x,
        item_inner.y,
        item_inner.w,
        item_inner.h,
        label=f"{index} 记忆中：{clip_result.name}",
        color=(0, 255, 0)
    )

    if string_match(clip_result.name, commodity_target, MatchConfig(fuzz_threshold=80)):
        _purchase_item(app, clip_result, item_inner)
        return True

    logger.debug(f"{clip_result.name} not in target list.")
    return False

def _handle_unknown_item(app, item_box, item_inner, commodity_target, index):
    """处理未知物品：点击 -> OCR -> 存库 -> 决策"""
    logger.debug(f"Item {index} not in memory, analyzing...")
    app.debug_tools.add_box(
        item_inner.x,
        item_inner.y,
        item_inner.w,
        item_inner.h,
        label=f"{index} 未知物品",
        color=(255, 0, 0)
    )

    # 点击打开模态
    modal = None
    for _ in range(3):
        app.device.click_element(item_box)
        sleep(0.5)
        app.game_utils.wait_loading()
        app.game_utils.wait_frame_stable()
        modal = app.game_utils.wait_for_modal(ModalText.TITLE.EXCHANGE_CONFIRMATION)
        if modal: break
    if not modal:
        return False
    # 提取信息
    try:
        yolo_result_item = copy(item_inner.frame)
        modal_item_image, item_info = modal_body_extract_item_info(modal.modal_body)
        ocr_results = ocr_service.ocr(item_info)
        valid_ocr = OCR_ResultList([res for res in ocr_results if len(res.text) > 2])

        if not valid_ocr:
            logger.warning("No OCR results found.")
            app.device.click_element(modal.cancel_button)
            return False

        item_name_ocr = valid_ocr.get_y_min()
        status, db_result = item_db.search(item_name_ocr.text)

        final_name = item_name_ocr.text

        # 存入记忆库
        if status:
            app.clip_manager.item_clip.add_to_memory(modal_item_image, db_result, 0.99)
            app.clip_manager.item_clip.add_to_memory(yolo_result_item, db_result, 0.99)
            final_name = db_result.name
        else:
            # 记录未知物品用于调试
            _save_debug_unknown_item(item_info, modal_item_image, modal.modal_body, index, final_name)

        # 购买决策
        if string_match(final_name, commodity_target, MatchConfig(fuzz_threshold=80)):
            logger.info(f"Purchase new item {final_name} (id={index})")
            app.device.click_element(modal.confirm_button)
        else:
            logger.debug(f"{final_name} not in target, cancel.")
            app.device.click_element(modal.cancel_button)

        app.game_utils.wait_label_exist(BaseUILabels.MODAL_HEADER)
        return True

    except Exception as e:
        logger.error(f"Error processing unknown item: {e}")
        if modal: app.device.click_element(modal.cancel_button)
        return False

def _save_debug_unknown_item(info_img, item_img, body_img, index, name):
    """保存识别失败的物品图片"""
    logger.warning(f"Item '{name}' not found in DB.")
    os.makedirs(DebugPath.UnknownItem, exist_ok=True)
    cv2.imwrite(os.path.join(DebugPath.UnknownItem, f"item_info_{index}.png"), info_img)
    cv2.imwrite(os.path.join(DebugPath.UnknownItem, f"modal_item_{index}.png"), item_img)

def _purchase_item(app: "AppProcessor", item_data, el: Yolo_Box):
    """购买物品"""
    logger.info(f"Purchase {item_data.name}...")
    for _ in range(3):
        app.device.click_element(el)
        app.game_utils.wait_frame_stable()
        modal = app.game_utils.wait_for_modal(ModalText.TITLE.EXCHANGE_CONFIRMATION)
        if modal:
            if modal.confirm_button.is_disabled():
                logger.warning("Insufficient resources")
                app.device.click_element(modal.cancel_button)
            else:
                app.device.click_element(modal.confirm_button)
            break
    app.game_utils.wait_label_exist(BaseUILabels.MODAL_HEADER)

def _scroll_page(app, scroll_x, scroll_y, item_commodity):
    """处理页面滚动"""
    if isinstance(app.device, Android_App):
        app.device.swipe(
            scroll_x,
            item_commodity.get_y_max_element().y,
            scroll_x,
            item_commodity.get_y_min_element().y
        )
    else:
        app.device.scrollY(scroll_x, scroll_y, -5)
    app.game_utils.wait_frame_stable()


def _wait_exchange_item_groups(
        app: "AppProcessor",
        timeout: float = 5.0,
        interval: float = 0.5,
) -> Tuple[Yolo_Results, List[Yolo_Results]]:
    """
    等待每日交换所商品列表出现，避免在页面未切换成功时继续执行。
    """
    waited = 0.0
    last_item_commodity = None
    last_item_groups = []
    while waited <= timeout:
        item_commodity = app.latest_results.filter_by_labels([BaseUILabels.ITEM, BaseUILabels.CARD_COMMODITY])
        item_groups = item_commodity.find_containing_groups(BaseUILabels.CARD_COMMODITY, [BaseUILabels.ITEM])
        if item_commodity and item_groups:
            return item_commodity, item_groups
        last_item_commodity = item_commodity
        last_item_groups = item_groups
        sleep(interval)
        waited += interval

    current_location = app.game_utils.update_current_location()
    raise RuntimeError(
        "Daily exchange commodity list not detected. "
        f"current_location={current_location}, "
        f"commodity_boxes={len(last_item_commodity) if last_item_commodity else 0}, "
        f"commodity_groups={len(last_item_groups)}"
    )

def _exchange_items(app: "AppProcessor", commodity_target: List[str]):
    """
    主循环：交换物品
    """
    logger.info(f"Shopping list: {commodity_target}")
    prev_page: Optional[np.ndarray] = None
    median_x, median_y = None, None

    # 检查内存是否为空，避免在空内存时进行无效检索
    is_memory_empty = len(CLIPMemory.select()) == 0

    while True:
        # 识别当前页面元素
        item_commodity, item_groups = _wait_exchange_item_groups(app)
        scroll_x, scroll_y = item_commodity.get_COL()

        # 初始化尺寸阈值（仅一次）
        if median_x is None:
            median_x, median_y = _calculate_median_size(item_groups)
            logger.debug(f"Median Size: w={median_x}, h={median_y}")

        # 遍历当前页面的所有物品
        for index, item_box in enumerate(item_groups):
            item_inner = item_box.filter_by_label(BaseUILabels.ITEM).first()

            # 有效性检查
            if not _is_valid_item(app, item_box, item_inner, median_x, median_y, index):
                continue

            # 尝试从记忆中检索
            clip_result = None
            if not is_memory_empty:
                clip_result = app.clip_manager.item_clip.retrieve(item_inner.frame, 0.99)

            if clip_result:
                # 记忆中存在
                _handle_known_item(app, item_inner, clip_result, commodity_target, index)
            else:
                # 记忆中不存在 (OCR + 更新记忆)
                _handle_unknown_item(app, item_box, item_inner, commodity_target, index)

            # 刷新调试显示
            app.debug_tools.show()
            sleep(0.5)

        # 翻页判断
        app.debug_tools.clear_all()
        if prev_page is not None and check_frame_change(prev_page, app.latest_frame):
            logger.info("Page content stable, end of list.")
            break

        prev_page = app.latest_frame.copy()
        _scroll_page(app, scroll_x, scroll_y, item_commodity)

def _find_visible_weekly_gift_buttons(app: "AppProcessor") -> List:
    # 只返回当前页真正可点击的“免费”礼包按钮。
    buttons = ButtonList(app.latest_results)
    return [
        button for button in buttons
        if button.text
        and string_match(button.text, ButtonText.FREE, MatchConfig(use_fuzz=False))
        and not button.is_disabled()
    ]


def _close_weekly_gift_result_modal(app: "AppProcessor") -> bool:
    # 领取确认后会再弹一次结果框；统一关掉后再继续扫描下一项。
    result_modal = app.game_utils.wait_for_modal(
        ModalText.TITLE.RECEIPT_COMPLETED,
        timeout=5,
        interval=0.5,
        no_body=True,
        match_config=MatchConfig(fuzz_threshold=90),
    )
    if result_modal is None:
        result_modal = app.game_utils.wait_for_modal(None, timeout=2, interval=0.5, no_body=True)
    if result_modal is None:
        logger.warning("Weekly gift result modal not found")
        return False

    close_button = result_modal.cancel_button or result_modal.confirm_button
    if close_button is None:
        logger.warning("Weekly gift result modal close button not found")
        return False

    app.device.click_element(close_button)
    app.game_utils.wait_label_exist(BaseUILabels.MODAL_HEADER, timeout=5, interval=0.5)
    app.game_utils.wait_frame_stable()
    return True


def _claim_weekly_gift_button(app: "AppProcessor", button) -> bool:
    # 单个礼包的流程固定为：点击礼包 -> 确认领取 -> 关闭结果弹窗。
    app.device.click_element(button)

    confirm_modal = app.game_utils.wait_for_modal(None, timeout=5, interval=0.5, no_body=True)
    if confirm_modal is None:
        logger.warning(f"Weekly gift confirm modal not found for button '{button.text}'")
        return False

    confirm_button = confirm_modal.confirm_button or confirm_modal.cancel_button
    if confirm_button is None:
        logger.warning("Weekly gift confirm modal action button not found")
        return False
    if confirm_button.is_disabled():
        logger.warning(f"Weekly gift button '{button.text}' is disabled after opening modal")
        return False

    app.device.click_element(confirm_button)
    return _close_weekly_gift_result_modal(app)


def _collect_visible_weekly_gifts(app: "AppProcessor") -> int:
    collected = 0
    skipped_signatures = set()

    while True:
        # 每次弹窗关闭后都重新取按钮，避免继续使用已经失效的 OCR/坐标结果。
        buttons = [
            button for button in _find_visible_weekly_gift_buttons(app)
            if (int(button.cx), int(button.cy), button.text) not in skipped_signatures
        ]
        if not buttons:
            return collected

        button = buttons[0]
        signature = (int(button.cx), int(button.cy), button.text)
        if _claim_weekly_gift_button(app, button):
            collected += 1
            skipped_signatures.clear()
            continue

        skipped_signatures.add(signature)
        app.game_utils.wait_frame_stable()


def _scroll_weekly_gift_page(app: "AppProcessor"):
    # 每次向下滚一屏左右，继续处理下一批可见礼包。
    height, width = app.latest_frame.shape[:2]
    if isinstance(app.device, Android_App):
        center_x = width // 2
        app.device.swipe(
            center_x,
            int(height * 0.82),
            center_x,
            int(height * 0.38),
            0.6,
        )
    else:
        app.device.scrollY(width // 2, height // 2, -20)
    app.game_utils.wait_frame_stable()


def action__receive_weekly_gift(app: "AppProcessor"):
    """领取每周礼包"""
    app.game_utils.click_button(ButtonText.SHOP.PACK, match_config=MatchConfig(use_fuzz=False))
    app.game_utils.wait_location_update(GamePageTypes.HOME_TAB.SHOP_SUB_PAGE.PACK)
    app.game_utils.wait_frame_stable()

    prev_page: Optional[np.ndarray] = None
    while True:
        # 先清空当前可视区域里的免费礼包，再决定是否继续翻页。
        collected = _collect_visible_weekly_gifts(app)
        logger.debug(f"Collected {collected} weekly gift packs on current page")

        current_page = app.latest_frame.copy()
        # 连续两页内容几乎不变时，说明已经滚到列表末尾。
        if prev_page is not None and check_frame_change(prev_page, current_page):
            break

        prev_page = current_page
        _scroll_weekly_gift_page(app)

    app.game_utils.back_next_page()
    app.game_utils.wait_loading()
    app.game_utils.update_current_location(GamePageTypes.HOME_TAB.SHOP)


def _reset_daily_exchange_to_top(app: "AppProcessor"):
    """
    刷新列表后回到商店主页再重新进入每日交换所，确保列表从顶部开始。
    """
    app.game_utils.back_next_page()
    app.game_utils.wait_location_update(GamePageTypes.HOME_TAB.SHOP)
    app.game_utils.wait_frame_stable()
    app.game_utils.click_button(ButtonText.SHOP.DAILY_EXCHANGE, match_config=MatchConfig(fuzz_threshold=90))
    app.game_utils.wait_location_update(GamePageTypes.HOME_TAB.SHOP_SUB_PAGE.DAILY_EXCHANGE)
    app.game_utils.wait_frame_stable()
    _wait_exchange_item_groups(app)


def _handle_tabbar__manny_exchange(app: "AppProcessor", commodity_target):
    refresh_shop = app.config_service().task__auto_purchase.refresh_shop.value
    use_gem_refresh = app.config_service().task__auto_purchase.use_gem_refresh.value
    height, width = app.latest_frame.shape[:2]
    remaining_attempts: Optional[int] = None
    remaining_attempts_match = re.compile(r".*更新可能回数 {,3}あと(\d+)回.*")
    while True:
        _exchange_items(app, commodity_target)
        if not refresh_shop:
            logger.debug("No need to refresh shop list")
            break
        buttons = ButtonList(app.latest_results)
        update_shop_btn = buttons.get_button_by_text(ButtonText.SHOP.LIST_UPDATE)
        logger.debug("update_shop_btn: {}".format(update_shop_btn))
        if not update_shop_btn:
            logger.warning("Not find update shop list button")
            break
        if string_match(update_shop_btn.text, ButtonText.FREE, MatchConfig(use_fuzz=False)):
            app.device.click_element(update_shop_btn)
            app.game_utils.wait_frame_stable()
            _reset_daily_exchange_to_top(app)
            continue
        if not use_gem_refresh:
            break
        if remaining_attempts is not None and remaining_attempts == 0:
            break
        app.device.click_element(update_shop_btn)
        app.game_utils.wait_frame_stable()
        modal_body: str = ""
        update_confirm_modal: Optional[Modal] = None
        for i in range(3):
            update_confirm_modal = app.game_utils.wait_for_modal(ModalText.TITLE.UPDATE_CONFIRM)
            if not update_confirm_modal:
                logger.error("Not find update confirm modal")
                break
            if update_confirm_modal.confirm_button.is_disabled():
                logger.warning("Unable to update the list: Insufficient gems available")
                break
            modal_body = update_confirm_modal.modal_body_text
            logger.debug("modal_body: {}".format(modal_body))
            if modal_body is not None:
                break
            logger.warning("Modal body is empty and is currently attempting to reacquire.")
            sleep(0.5)
        if remaining_attempts is None:
            m1 = remaining_attempts_match.match(modal_body)
            if not m1:
                break
            remaining_attempts = int(m1.group(1))
            logger.debug(f"remaining attempts: {remaining_attempts}")
        app.device.click_element(update_confirm_modal.confirm_button)
        app.game_utils.wait_loading()
        app.game_utils.wait_frame_stable()
        remaining_attempts -= 1
        _reset_daily_exchange_to_top(app)


def action__daily_exchange(app: "AppProcessor"):
    app.game_utils.click_button(ButtonText.SHOP.DAILY_EXCHANGE, match_config=MatchConfig(fuzz_threshold=90))
    app.game_utils.wait_location_update(GamePageTypes.HOME_TAB.SHOP_SUB_PAGE.DAILY_EXCHANGE)
    _wait_exchange_item_groups(app)
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
    for index, tab_item in enumerate(tabbar):
        app.device.click_element(tab_item)
        app.game_utils.wait_frame_stable()
        # if string_match(tab_item.text, "マニー"):
        match index:
            case 0:
                _handle_tabbar__manny_exchange(app, commodity_target)
            case _:
                _exchange_items(app, commodity_target)
    return True
