import time

from src.constants.game.text.modal_text import ModalText
from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.core.device.Android.app import Android_App
from src.core.device.windows_compat import is_windows_device
from time import sleep

from src.entity.Game.Page.Types.index import GamePageTypes
from src.utils.debug_tools import DebugTools
from src.utils.logger import logger
from typing import TYPE_CHECKING

from src.utils.opencv_tools import is_white_screen

if TYPE_CHECKING:
    from src.main import AppProcessor

GAME_RUNNING = False
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
                if is_windows_device(processor.device):
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
        from src.core.tasks.base_ui.start_game import (
            action__click_start_game,
            action__wait_enter_home,
        )

        sleep(2)
        if not app.game_utils.update_current_location() == GamePageTypes.START_GAME:
            return
        action__click_start_game(app)
        app.game_utils.wait_loading()
        action__wait_enter_home(app)
        app.game_utils.update_current_location()

    @processor.task_queue.register_task("get_expenditure", "获取活动费", 30)
    def _task__get_expenditure(app: "AppProcessor"):
        from src.core.tasks.base_ui.goto_pages import goto__get_expenditure

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
        from src.core.tasks.base_ui.dispatch_work import (
            action__dispatch_all_available_work,
            handle__work_dispatch_results,
        )
        from src.core.tasks.base_ui.goto_pages import goto__work_dispatch_page

        goto__work_dispatch_page(app)
        handle__work_dispatch_results(app)
        action__dispatch_all_available_work(app)

    @processor.task_queue.register_task("get_gift", "获取礼物/邮箱")
    def _task__get_gift(app: "AppProcessor"):
        from src.core.tasks.base_ui.get_gift import (
            action__collect_all_gifts,
            action__has_gift_items,
        )
        from src.core.tasks.base_ui.goto_pages import goto__gift_page

        goto__gift_page(app)
        if action__has_gift_items(app):
            action__collect_all_gifts(app)

    @processor.task_queue.register_task("auto_purchase", "自动每日交换")
    def _task__automated_purchase(app: "AppProcessor"):
        from src.core.tasks.base_ui.auto_purchase import (
            action__daily_exchange,
            action__receive_weekly_gift,
        )
        from src.core.tasks.base_ui.goto_pages import goto__shop_page

        goto__shop_page(app)
        if app.config_service().task__auto_purchase.weekly_gift.value:
            action__receive_weekly_gift(app)
        action__daily_exchange(app)

    @processor.task_queue.register_task("auto_enhancement_support_card", "自动强化支援卡")
    def _task__auto_enhancement_support_card(app: "AppProcessor"):
        from src.core.tasks.base_ui.goto_pages import goto_support_card_list_page

        goto_support_card_list_page(app)
        app.game_utils.wait_frame_stable()
        support_cards = app.latest_results.filter_by_label(BaseUILabels.SUPPORT_CARD)
        buttons = app.latest_results.filter_by_label(BaseUILabels.BUTTON)
        # support_cards = support_cards.from_boxes([
        #     card for card in support_cards
        #     if any(
        #         card.x <= btn.cx <= card.w
        #         for btn in buttons
        #     )
        # ])
        # logger.debug(f"found {len(support_cards)} cards: {support_cards}")
        debug_tools.clear_all()
        logger.debug(f"buttons: {buttons}")
        for card in support_cards:
            logger.debug(f"support card: {card}, bool={any(btn.cy >= card.y and btn.cy <= card.h for btn in buttons)}")
            if any(card.y <= btn.cy <= card.h for btn in buttons):
                continue
            debug_tools.add_box(card.x, card.y, card.w, card.h)

    @processor.task_queue.register_task("auto_contest", "自动每日竞技场")
    def _task__automated_contest(app: "AppProcessor"):
        from src.core.tasks.base_ui.auto_contest import (
            action__check_and_collect_rewards,
            action__loop_challenge_contest,
        )
        from src.core.tasks.base_ui.goto_pages import goto__contest_page

        goto__contest_page(app)
        sleep(3)
        action__check_and_collect_rewards(app)
        action__loop_challenge_contest(app)

    @processor.task_queue.register_task("claim_task_rewards", "领取任务奖励")
    def _task__claim_task_rewards(app: "AppProcessor"):
        from src.core.tasks.base_ui.claim_task_rewards import claim_task_rewards
        from src.core.tasks.base_ui.goto_pages import goto__claim_task_rewards_page

        goto__claim_task_rewards_page(app)
        claim_task_rewards(app)

    @processor.task_queue.register_task("claim_pass_rewards", "领取通行证奖励")
    def _task__claim_pass_rewards(app: "AppProcessor"):
        from src.core.tasks.base_ui.claim_pass_rewards import claim_pass_rewards
        from src.core.tasks.base_ui.goto_pages import goto__claim_pass_rewards

        goto__claim_pass_rewards(app)
        claim_pass_rewards(app)

    # @processor.task_queue.register_task("auto_producer", "自动培育")
    # def _task__auto_producer(app: "AppProcessor"):
    #     pass

    @processor.task_queue.register_task("void_task", "测试任务", hide=True)
    def _task__void_task(app: "AppProcessor"):
        logger.success("void_task!")
        return True

    @processor.task_queue.register_task("refresh_skill_storage", "刷新技能卡存储", disabled_middleware=True, manual_only=True, allow_manual_resume=True)
    def _task__refresh_skill_storage(app: "AppProcessor"):
        from src.core.tasks.base_ui.refresh_skill_storage import refresh_skill_storage

        refresh_skill_storage(app)
