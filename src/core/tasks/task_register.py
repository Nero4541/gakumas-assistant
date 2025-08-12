
from src.core.tasks.base_ui.auto_contest import action__check_and_collect_rewards, \
    action__loop_challenge_contest
from src.core.tasks.base_ui.automated_purchase import action__receive_weekly_gift, action__daily_exchange
from src.core.tasks.base_ui.claim_task_rewards import claim_task_rewards
from src.core.tasks.base_ui.dispatch_work import handle__work_dispatch_results, action__dispatch_all_available_work
from src.core.tasks.base_ui.get_gift import action__has_gift_items, action__collect_all_gifts
from src.core.tasks.base_ui.goto_pages import goto__get_expenditure, goto__work_dispatch_page, goto__gift_page, \
    goto__shop_page, goto__contest_page, goto__claim_task_rewards_page
from src.core.tasks.base_ui.start_game import (
    action__click_start_game,
    action__wait_enter_home
)
from src.entity.Game.Components.TabBar import TabBar
from time import sleep
from src.entity.Game.Page.Types.index import GamePageTypes
from src.constants import *
from src.utils.logger import logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.main import AppProcessor

def register_tasks(processor: "AppProcessor"):
    @processor.register_task("start_game", "启动游戏", 120, disabled_middleware=True)
    def _task__start_game(app: "AppProcessor"):
        if not app.game_utils.update_current_location() == GamePageTypes.START_GAME:
            return
        action__click_start_game(app)
        app.game_utils.wait_loading()
        action__wait_enter_home(app)
        app.game_utils.update_current_location()

    @processor.register_task("get_expenditure", "获取活动费", 30)
    def _task__get_expenditure(app: "AppProcessor"):
        goto__get_expenditure(app)
        sleep(3)
        if modal := app.game_utils.wait_for_modal(modal_text.expenditure, no_body=True, timeout=10):
            app.app.click_element(modal.cancel_button)
            sleep(3)
            return True
        elif app.latest_results.exists_label(base_labels.tab_home):
            logger.warning("There are no claimable expenses")
            return True
        raise TimeoutError("Timeout waiting for modal to appear.")

    @processor.register_task("dispatch_work", "派遣任务", 120)
    def _task__work_dispatch(app: "AppProcessor"):
        goto__work_dispatch_page(app)
        handle__work_dispatch_results(app)
        action__dispatch_all_available_work(app)

    @processor.register_task("get_gift", "获取礼物/邮箱")
    def _task__get_gift(app: "AppProcessor"):
        goto__gift_page(app)
        if action__has_gift_items(app):
            action__collect_all_gifts(app)

    @processor.register_task("automated_purchase", "自动每日交换")
    def _task__automated_purchase(app: "AppProcessor"):
        goto__shop_page(app)
        if app.config_service().task__auto_purchase.weekly_gift.value:
            action__receive_weekly_gift(app)
        commodity_target = app.config_service().task__auto_purchase.daily_buy_list
        action__daily_exchange(app, commodity_target)

    @processor.register_task("automated_contest", "自动每日竞技场")
    def _task__automated_contest(app: "AppProcessor"):
        goto__contest_page(app)
        action__check_and_collect_rewards(app)
        action__loop_challenge_contest(app)

    @processor.register_task("claim_task_rewards", "领取任务奖励")
    def _task__claim_task_rewards(app: "AppProcessor"):
        goto__claim_task_rewards_page(app)
        claim_task_rewards(app)

