import cv2
import numpy as np

from src.core.CLIP_services.item import ItemInfo
from src.core.tasks.base_ui.auto_contest import action__enter_contest_page, action__check_and_collect_rewards, \
    action__loop_challenge_contest
from src.core.tasks.base_ui.dispatch_work import action__enter_dispatch_page, action__dispatch_all_available_work
from src.core.tasks.base_ui.get_gift import action__enter_gift_page, action__has_gift_items, action__collect_all_gifts
from src.core.tasks.base_ui.start_game import (
    action__click_start_game,
    handle__network_error_modal_boxes,
    action__check_home_tab_exist
)
from src.entity.Game.Components.Button import Button, ButtonList
from src.entity.Game.Components.CheckBox import CheckBox
from src.entity.Game.Components.Contest import ContestList
from src.entity.Game.Components.TabBar import TabBar
from src.entity.Yolo import Yolo_Box
from src.utils.game_tools import get_current_location, modal_body_extract_item_info
from time import sleep
from src.entity.Game.Page.Types.index import GamePageTypes
from src.constants import *
from src.utils.logger import logger
from typing import TYPE_CHECKING

from src.utils.ocr_instance import get_ocr, OCRService, OCR_ResultList
from src.utils.opencv_tools import check_color_in_region
from src.utils.string_tools import string_match, MatchConfig
from src.utils.yolo_tools import get_modal

if TYPE_CHECKING:
    from app import AppProcessor

def register_tasks(processor: "AppProcessor"):
    @processor.register_task("start_game", "启动游戏", 60)
    @logger.catch
    def _task__start_game(app: "AppProcessor"):
        TIMEOUT = 30
        if not (app.game_status_manager.current_location == GamePageTypes.START_GAME or app.latest_results.exists_label(base_labels.start_menu_logo)):
            return
        if action__click_start_game(app, TIMEOUT) is not False:
            sleep(2)
            app.game_utils.wait_loading()
            handle__network_error_modal_boxes(app)
        action__check_home_tab_exist(app)
        app.game_utils.update_current_location()

    @processor.register_task("get_expenditure", "获取活动费", 30)
    @logger.catch
    def _task__get_expenditure(app: "AppProcessor"):
        app.game_utils.go_home()
        app.game_utils.wait_loading()
        if not app.game_utils.wait_for_label(base_labels.home_get_expenditure):
            raise TimeoutError("Timeout waiting for [home:expenditure] to appear.")
        app.app.click_element(app.latest_results.filter_by_label(base_labels.home_get_expenditure).first())
        sleep(3)
        if modal := app.game_utils.wait_for_modal(modal_text.expenditure, no_body=True, timeout=10):
            app.app.click_element(modal.cancel_button)
            sleep(3)
            return True
        elif app.latest_results.exists_label(base_labels.tab_home):
            logger.warning("There are no claimable expenses")
            return True
        raise TimeoutError("Timeout waiting for modal to appear.")

    @processor.register_task("dispatch_work", "派遣任务", 30)
    @logger.catch
    def _task__dispatch_work(app: "AppProcessor"):
        app.game_utils.go_home()
        app.game_utils.wait_loading()
        action__enter_dispatch_page(app)
        action__dispatch_all_available_work(app)

    @processor.register_task("get_gift", "获取礼物/邮箱")
    @logger.catch
    def _task__get_gift(app: "AppProcessor"):
        app.game_utils.go_home()
        app.game_utils.wait_loading()
        action__enter_gift_page(app)
        if action__has_gift_items(app):
            action__collect_all_gifts(app)

    @processor.register_task("automated_purchase", "自动每日交换")
    @logger.catch
    def _task__automated_purchase(app: "AppProcessor"):
        app.game_utils.go_home()
        app.game_utils.wait_loading()
        app.game_utils.click_on_label(base_labels.home_shop_btn)
        app.game_utils.wait_loading()
        app.game_utils.update_current_location(GamePageTypes.HOME_TAB.SHOP)
        # 领取每周礼包
        app.game_utils.click_button("パック")
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
        # 每日兑换
        app.game_utils.click_button("デイリー交換所")
        app.game_utils.wait_for_label(base_labels.card__commodity)
        app.game_utils.update_current_location(GamePageTypes.HOME_TAB.SHOP_SUB_PAGE.DAILY_EXCHANGE)
        commodity_target = ["アノマリーノート"]
        ocr_service = OCRService()
        # 上一次获取到的列表哈希
        last_list_hash = None
        while True:
            # 当前页面物品（名）列表
            current_list = []
            item_commodity = app.latest_results.filter_by_labels([base_labels.item,base_labels.card__commodity])
            item_commodity_group = item_commodity.find_containing_groups(base_labels.card__commodity, [base_labels.item])
            scroll_x, scroll_y = item_commodity.get_COL()
            # 循环每一个物品
            for index, result in enumerate(item_commodity_group):
                item = result.filter_by_label(base_labels.item).first()
                # 跳过无法交换的物品
                if ocr_service.ocr(item.frame).search("交換済み"):
                    continue
                # 如果已经在记忆中
                if clip_result := app.clip_manager.item_clip.retrieve(item.frame, 0.97):
                    # 在购买列表中
                    if string_match(clip_result.name, commodity_target, MatchConfig(fuzz_threshold=80)):
                        app.app.click_element(result)
                        modal = app.game_utils.wait_for_modal(modal_text.exchange_confirmation)
                        app.app.click_element(modal.confirm_button)
                    current_list.append(clip_result.name)
                # 不在记忆中
                else:
                    app.app.click_element(result)
                    modal = app.game_utils.wait_for_modal(modal_text.exchange_confirmation)
                    yolo_result_item = item.frame
                    # 截取物品和物品信息
                    item, item_info = modal_body_extract_item_info(modal.modal_body)
                    ocr_results = ocr_service.ocr(item_info)
                    ocr_results = OCR_ResultList([res for res in ocr_results if len(res.text) > 2])
                    item_name = ocr_results.get_y_min()
                    item_info = ocr_results.exclude([item_name])
                    item_name = item_name.text
                    item_info = ItemInfo(item_name, [_.text for _ in item_info])
                    # 添加到记忆中
                    app.clip_manager.item_clip.add_to_memory(item, item_info)
                    app.clip_manager.item_clip.add_to_memory(yolo_result_item, item_info)
                    current_list.append(item_name)
                    # 在购买列表的情况下购买
                    if string_match(item_name, commodity_target, MatchConfig(fuzz_threshold=80)):
                        app.app.click_element(modal.confirm_button)
                    else:
                        app.app.click_element(modal.cancel_button)
                    sleep(0.5)
            # 如果历史哈希不相同，则向下滚动
            if last_list_hash != hash(frozenset(current_list)):  # 使用哈希值进行比较
                logger.debug(current_list)
                last_list_hash = hash(frozenset(current_list))
                app.app.scrollY(scroll_x,scroll_y,-5)
            else:
                break

            # commodity_box = result.filter_by_label(base_labels.card__commodity).first()
            # cv2.imshow(f"[{index}]item_exchange", item_exchange.filter_by_label(base_labels.card__commodity).first().frame)
        # cv2.waitKey(0)

    @processor.register_task("automated_contest", "自动每日竞技场")
    @logger.catch
    def _task__automated_contest(app: "AppProcessor"):
        app.game_utils.go_home()
        app.game_utils.wait_loading()
        action__enter_contest_page(app)
        action__check_and_collect_rewards(app)
        action__loop_challenge_contest(app)

    @processor.register_task("claim_task_rewards", "领取任务奖励")
    @logger.catch
    def _task__claim_task_rewards(app: "AppProcessor"):
        app.game_utils.go_home()
        app.game_utils.wait_loading()
        app.game_utils.click_on_label(base_labels.home_daily_task)
        app.game_utils.wait_for_label(base_labels.tab_bar)
        tab_bar = TabBar(app.latest_results.filter_by_label(base_labels.tab_bar).first())
        logger.debug(tab_bar)
        height, width = app.latest_frame.shape[:2]
        frame_cx = width // 2
        for tab in tab_bar:
            app.app.click_element(tab)
            sleep(3)
            buttons = app.latest_results.filter_by_label(base_labels.button)
            flag = False
            for button in buttons:
                if frame_cx - 10 < button.cx < frame_cx + 10 and not Button(button).is_disabled():
                    app.app.click_element(button)
                    flag = True
                    break
            if flag:
                modal = app.game_utils.wait_for_modal(modal_text.receipt_completed, no_body=True, timeout=10)
                app.app.click_element(modal.cancel_button)
                app.game_utils.click_on_label(base_labels.close_button)
                logger.info(f"The task reward of {tab.text} has been claimed")
            else:
                logger.info(f"{tab.text} has no task rewards to be claimed")
            sleep(1)

