import os
import time
from copy import copy

import cv2
import numpy as np

from src.constants.game.text.button_text import ButtonText
from src.constants.game.text.modal_text import ModalText
from src.constants.path.debug_path import DebugPath
from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.core.device.Android.app import Android_App
from src.core.device.Windows.app import Windows_App
from src.core.inference.ocr_engine import OCRService, OCR_ResultList
from src.core.tasks.base_ui.auto_contest import action__check_and_collect_rewards, \
    action__loop_challenge_contest
from src.core.tasks.base_ui.auto_purchase import action__receive_weekly_gift, action__daily_exchange
from src.core.tasks.base_ui.claim_pass_rewards import claim_pass_rewards
from src.core.tasks.base_ui.claim_task_rewards import claim_task_rewards
from src.core.tasks.base_ui.dispatch_work import handle__work_dispatch_results, action__dispatch_all_available_work
from src.core.tasks.base_ui.get_gift import action__has_gift_items, action__collect_all_gifts
from src.core.tasks.base_ui.goto_pages import goto__get_expenditure, goto__work_dispatch_page, goto__gift_page, \
    goto__shop_page, goto__contest_page, goto__claim_task_rewards_page, goto__claim_pass_rewards
from src.core.tasks.base_ui.start_game import (
    action__click_start_game,
    action__wait_enter_home
)
from time import sleep

from src.entity.Game.Components.Button import ButtonList
from src.entity.Game.Components.CheckBox import CheckBox
from src.entity.Game.Components.TabBar import TabBar
from src.entity.Game.Page.Types.index import GamePageTypes
from src.entity.Yolo import Yolo_Box
from src.utils.debug_tools import DebugTools
from src.utils.game_database_tools import GakumasDatabase_ProduceCardDataUtils
from src.utils.logger import logger
from typing import TYPE_CHECKING, Optional

from src.utils.opencv_tools import is_white_screen, get_mask_contours, check_frame_change
from src.utils.string_tools import string_match, MatchConfig
from src.utils.ui_message_tools import UIMessage

if TYPE_CHECKING:
    from src.main import AppProcessor

GAME_RUNNING = False
message_tools = UIMessage()
debug_tools = DebugTools()

def register_tasks(processor: "AppProcessor"):

    @processor.task_queue.register_pre_queue_start()
    def _pre__check_adb_connect():
        """
        检查ADB连接并尝试重连
        :return:
        """
        def _check():
            try:
                logger.debug(f"device bool: {bool(processor.device)}, try capture size={processor.device.capture().size}")
                return bool(processor.device) and processor.device.capture().size != 0
            except Exception as e:
                logger.warning(f"screen capture test failed: {e}")
                return False
        if isinstance(processor.device, Android_App):
            MAX_TRY = 3
            TRY_COUNT = 0
            while TRY_COUNT < MAX_TRY:
                if not _check():
                    logger.warning(f"[{TRY_COUNT}]Adb connect disconnect, Try reconnect")
                    processor.create_device_instance()
                else:
                    logger.success(f"Adb reconnection was successful")
                    return True
                sleep(1)
                TRY_COUNT += 1
            logger.error(f"The maximum number of adb reconnections has been reached")
            return False
        return True

    @processor.task_queue.register_pre_queue_start()
    def _pre__resume_yolo_inference():
        if processor.yolo_engine.running:
            return True
        processor.yolo_engine.start()
        processor.yolo_engine.resume()
        return True

    @processor.task_queue.register_pre_queue_start()
    def _pre__wait_frame():
        TIMEOUT = 30
        START_TIME = time.time()
        while True:
            if time.time() - START_TIME > TIMEOUT:
                raise TimeoutError()
            if processor.yolo_engine.latest_frame is None:
                sleep(0.25)
                continue
            if processor.yolo_engine.latest_frame.size != 0:
                break

    @processor.task_queue.register_pre_queue_start()
    def _pre__start_game():
        global GAME_RUNNING
        GAME_RUNNING = False
        TIMEOUT = 120
        COUNT = 0
        if not processor.config_service().base.auto_start_game.value:
            return True
        logger.debug(f"Game running: {processor.device.is_app_running()}")
        if processor.device.is_app_running():
            GAME_RUNNING = True
            # 将游戏切换到前台
            if not processor.device.is_app_focused():
                logger.debug(f"Game switch to front......")
                if isinstance(processor.device, Windows_App):
                    processor.device.bring_to_front()
                else:
                    processor.device.start_game()

                    # 检测白屏
                    start_time = time.time()
                    while time.time() - start_time < 3:
                        screenshot = processor.device.capture()  # 截取屏幕
                        if is_white_screen(screenshot):
                            logger.debug("White screen detected, setting GAME_RUNNING to False.")
                            GAME_RUNNING = False
                            return True
            sleep(1)  # 每秒检查一次
            return True
        processor.device.start_game()
        while not processor.device.is_app_running():
            if COUNT >= TIMEOUT:
                return False
            COUNT += 1
            sleep(1)
        return True

    @processor.task_queue.register_pre_queue_start()
    def _pre__resume_yolo_engine():
        """恢复Yolo引擎"""
        if processor.yolo_engine.running is False:
            processor.yolo_engine.start()
        processor.yolo_engine.resume()

    @processor.task_queue.register_pre_queue_start()
    def _pre__wait_game_start():
        """等待游戏启动"""
        TIMEOUT = 120
        COUNT = 0
        if GAME_RUNNING:
            return True
        logger.debug("wait game start......")
        while not processor.latest_results.exists_label(BaseUILabels.START_MENU_LOGO):
            if COUNT >= TIMEOUT:
                return False
            COUNT += 1
            sleep(1)
        return True

    @processor.task_queue.register_task("start_game", "启动游戏", 3600, disabled_middleware=True)
    def _task__start_game(app: "AppProcessor"):
        sleep(2)
        if not app.game_utils.update_current_location() == GamePageTypes.START_GAME:
            return
        action__click_start_game(app)
        app.game_utils.wait_loading()
        action__wait_enter_home(app)
        app.game_utils.update_current_location()

    @processor.task_queue.register_task("get_expenditure", "获取活动费", 30)
    def _task__get_expenditure(app: "AppProcessor"):
        goto__get_expenditure(app)
        sleep(3)
        if modal := app.game_utils.wait_for_modal(ModalText.TITLE.EXPENDITURE, no_body=True, timeout=10):
            app.device.click_element(modal.cancel_button)
            sleep(3)
            return True
        elif app.latest_results.exists_label(BaseUILabels.TAB_HOME):
            logger.warning("There are no claimable expenses")
            return True
        raise TimeoutError("Timeout waiting for modal to appear.")

    @processor.task_queue.register_task("dispatch_work", "派遣任务", 120)
    def _task__work_dispatch(app: "AppProcessor"):
        goto__work_dispatch_page(app)
        handle__work_dispatch_results(app)
        action__dispatch_all_available_work(app)

    @processor.task_queue.register_task("get_gift", "获取礼物/邮箱")
    def _task__get_gift(app: "AppProcessor"):
        goto__gift_page(app)
        if action__has_gift_items(app):
            action__collect_all_gifts(app)

    @processor.task_queue.register_task("auto_purchase", "自动每日交换")
    def _task__automated_purchase(app: "AppProcessor"):
        goto__shop_page(app)
        if app.config_service().task__auto_purchase.weekly_gift.value:
            action__receive_weekly_gift(app)
        action__daily_exchange(app)

    @processor.task_queue.register_task("auto_contest", "自动每日竞技场")
    def _task__automated_contest(app: "AppProcessor"):
        goto__contest_page(app)
        sleep(3)
        action__check_and_collect_rewards(app)
        action__loop_challenge_contest(app)

    @processor.task_queue.register_task("claim_task_rewards", "领取任务奖励")
    def _task__claim_task_rewards(app: "AppProcessor"):
        goto__claim_task_rewards_page(app)
        claim_task_rewards(app)

    @processor.task_queue.register_task("claim_pass_rewards", "领取通行证奖励")
    def _task__claim_pass_rewards(app: "AppProcessor"):
        goto__claim_pass_rewards(app)
        claim_pass_rewards(app)

    @processor.task_queue.register_task("void_task", "测试任务")
    def _task__void_task(app: "AppProcessor"):
        logger.success("void_task!")
        return True

    @processor.task_queue.register_task("refresh_skill_storage", "刷新技能卡存储", disabled_middleware=True, manual_only=True, allow_manual_resume=True)
    def _task__refresh_skill_storage(app: "AppProcessor"):
        while True:
            # logger.debug(app.latest_results)
            if app.game_utils.update_current_location() != GamePageTypes.SUB_MENU.PRODUCER_ILLUSTRATED:
                message_tools.info("任务已挂起，请手动切换到图鉴页面", 30)
                # app.task_queue.insert_task_to_run_queue("void_task")
                app.task_queue.suspend_running_task()
            else:
                break
        if app.game_utils.wait_for_label(BaseUILabels.TAB_BAR):
            tabbar = TabBar(app.latest_results.filter_by_label(BaseUILabels.TAB_BAR).first())
            for tab_item in tabbar:
                if string_match(tab_item.text, "スキルカード"):
                    app.device.click_element(tab_item)
                    break
        else:
            message_tools.error("无法找到TabBar，刷新失败")
            return False
        if not app.game_utils.wait_for_label(BaseUILabels.BUTTON):
            logger.error("not find task require button, refresh fail")
            message_tools.error("无法找到任务所需的按钮，刷新失败")
            return False
        buttons = ButtonList(app.latest_results)
        switch_intensify_effect = buttons.get_button_by_text("強化") or next((string_match(i.text, "強化") for i in [CheckBox(el) for el in app.latest_results.filter_by_label(BaseUILabels.CHECKBOX)]))
        idol_switch = buttons.get_button_by_text("切り替え")
        if not switch_intensify_effect:
            logger.error("not find switch_intensify_effect button, refresh fail")
            message_tools.error("无法找到卡属性切换按钮，刷新失败")
            return False
        if not idol_switch:
            logger.error("not find idol_switch button, refresh fail")
            message_tools.error("无法找到偶像切换按钮，刷新失败")
            return False


        # TODO 外部服务，待拆走
        ocr_service = OCRService()
        skill_card_database = GakumasDatabase_ProduceCardDataUtils()

        os.makedirs(DebugPath.NoValidSkillCardInfo, exist_ok=True)
        width, _ = app.device.get_window_size()
        skill_card_form_info_box: Optional[Yolo_Box] = None
        prev_page: Optional[np.ndarray] = None
        swipe_start: int = 0
        swipe_end: int = 0

        while True:
            skill_cards = app.latest_results.filter_by_labels([BaseUILabels.SKILL_CARD, BaseUILabels.SKILL_CARD_ACTIVE, BaseUILabels.SKILL_CARD_MENTAL, BaseUILabels.SKILL_CARD_TRAP])
            skill_card_list = skill_cards.remove_by_yolo_results(skill_cards.get_y_min_element())
            if skill_card_form_info_box is None:
                skill_card_form_info_box = skill_cards.get_y_min_element()
            if not swipe_start or not swipe_end:
                swipe_start = skill_card_list.get_y_max_element().get_COL()[1]
                swipe_end = skill_card_list.get_y_min_element().get_COL()[1]
                logger.debug(f"swipe_start={swipe_start}, swipe_end={swipe_end}")
                debug_tools.add_line(0, swipe_start, width, swipe_start, color=(0,255,0))
                debug_tools.add_line(0, swipe_end, width, swipe_end, color=(0,255,255))
            for index, skill_card in enumerate(skill_card_list):
                debug_tools.add_box(skill_card.x, skill_card.y, skill_card.w, skill_card.h)

                app.device.click_element(skill_card)
                sleep(1)
                app.game_utils.wait_frame_stable(stable_count=2)
                skill_card_image = app.latest_frame[skill_card_form_info_box.y:skill_card_form_info_box.h, skill_card_form_info_box.x:skill_card_form_info_box.w]
                skill_card_info_image = app.latest_frame[skill_card_form_info_box.y - 10:skill_card_form_info_box.h, skill_card_form_info_box.w:]
                if app.clip_manager.skill_card_clip.retrieve(skill_card_image) is not None:
                    continue
                ocr_result = ocr_service.ocr(skill_card_info_image)
                if ocr_result is None:
                    logger.warning("No valid skill card information.")
                    continue
                ocr_result.auto_merge_lines(width_gap=100)
                card_title = ocr_result.get_y_min().text
                logger.debug(card_title)
                status, db_search_result = skill_card_database.search(card_title)
                if not status:
                    logger.warning("No search skill card info form game database.")
                    continue
                logger.debug(db_search_result)
                app.clip_manager.skill_card_clip.add_to_memory(skill_card_image, db_search_result)
                # app.clip_manager.skill_card_clip.add_to_memory(skill_card.frame, db_search_result)
                sleep(2)

            if isinstance(app.device, Android_App):
                app.device.swipe(width // 2, swipe_start, width // 2, swipe_end, offset_y=0)
            sleep(1)
            app.game_utils.wait_frame_stable()

            debug_tools.clear_all()

            if prev_page is not None and check_frame_change(prev_page, app.latest_frame):
                break

            prev_page = app.latest_frame