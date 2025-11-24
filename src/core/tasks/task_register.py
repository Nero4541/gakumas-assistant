from src.constants.text.button_text import ButtonText
from src.constants.text.modal_text import ModalText
from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.core.tasks.base_ui.auto_contest import action__check_and_collect_rewards, \
    action__loop_challenge_contest
from src.core.tasks.base_ui.auto_purchase import action__receive_weekly_gift, action__daily_exchange
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
from src.entity.Game.Page.Types.index import GamePageTypes
from src.utils.game_tools import get_modal
from src.utils.logger import logger
from typing import TYPE_CHECKING

from src.utils.string_tools import string_match, MatchConfig

if TYPE_CHECKING:
    from src.main import AppProcessor

GAME_RUNNING = False

def register_tasks(processor: "AppProcessor"):

    @processor.task_queue.register_pre_queue_start()
    def _pre__start_game():
        global GAME_RUNNING
        GAME_RUNNING = False
        TIMEOUT = 120
        COUNT = 0
        if not processor.config_service().base.auto_start_game.value:
            return
        logger.debug(f"Game running: {processor.device.is_app_running()}")
        if processor.device.is_app_running():
            GAME_RUNNING = True
            return
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
            return
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
        y, x = app.latest_results.frame.shape[:2]
        while True:
            buttons = ButtonList(app.latest_results)
            flag = True
            for button in buttons:
                if not button.is_disabled() and string_match(button.text, ButtonText.COLLECT, MatchConfig(fuzz_threshold=90)):
                    flag = False
                    app.device.click_element(button)
                    MAX_WAIT_TIME = 5
                    for i in range(MAX_WAIT_TIME + 1):
                        if MAX_WAIT_TIME < i:
                            raise TimeoutError("Timeout waiting for modal to appear.")
                        if app.latest_results.exists_all_labels([BaseUILabels.BUTTON, BaseUILabels.MODAL_HEADER]):
                            modal = get_modal(app.latest_results, True)
                            if string_match(modal.modal_title, ModalText.TITLE.RECEIPT_COMPLETED):
                                app.device.click_element(modal.cancel_button)
                                break
                            elif string_match(modal.modal_title, ModalText.TITLE.CONNECTION_ERROR):
                                app.device.click_element(modal.confirm_button)
                            else:
                                app.device.click_element(modal.cancel_button)
                        sleep(1)
                    app.game_utils.wait_for_label(BaseUILabels.CURRENT_LOCATION)
                    sleep(1)
            app.device.scrollY(x // 2, y // 2, -20)
            if flag:
                break
