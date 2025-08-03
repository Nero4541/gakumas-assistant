from src.constants import *
from typing import TYPE_CHECKING
from src.entity.Game.Page.Types.index import GamePageTypes

if TYPE_CHECKING:
    from src.main import AppProcessor

def _back_home(app: "AppProcessor"):
    if app.game_utils.update_current_location() != GamePageTypes.MAIN_MENU__HOME:
        app.game_utils.go_home()
        # app.game_utils.wait_loading()
        app.game_utils.wait_location_update(GamePageTypes.MAIN_MENU__HOME)

def _goto_tab_contest(app: "AppProcessor"):
    if app.game_utils.update_current_location() == GamePageTypes.MAIN_MENU__CONTEST:
        return
    _back_home(app)
    if not app.game_utils.wait_for_label(base_labels.tab_contest):
        raise TimeoutError("Timeout waiting for [tab:contest] to appear.")
    app.game_utils.click_on_label(base_labels.tab_contest)
    app.game_utils.wait_location_update(GamePageTypes.MAIN_MENU__CONTEST)

def goto__get_expenditure(app: "AppProcessor"):
    """ 进入“活动费”领取菜单 """
    _back_home(app)
    if not app.game_utils.wait_for_label(base_labels.home_get_expenditure):
        raise TimeoutError("Timeout waiting for [home:expenditure] to appear.")
    app.game_utils.click_on_label(base_labels.home_get_expenditure)

def goto__work_dispatch_page(app: "AppProcessor"):
    """ 进入任务派遣页面 """
    _back_home(app)
    if not app.game_utils.wait_for_label(base_labels.home_dispatch_work):
        raise TimeoutError("Timeout waiting for [home:dispatch work] to appear.")
    app.game_utils.click_on_label(base_labels.home_dispatch_work)
    app.game_utils.wait_loading()

def goto__gift_page(app: "AppProcessor"):
    """ 进入礼物领取页面 """
    _back_home(app)
    if not app.game_utils.wait_for_label(base_labels.home_gift_btn):
        raise TimeoutError("Timeout waiting for [home:gift] to appear.")
    app.game_utils.click_on_label(base_labels.home_gift_btn)
    app.game_utils.wait_location_update(GamePageTypes.HOME_TAB.GIFT)

def goto__shop_page(app: "AppProcessor"):
    """ 进入商店页面 """
    _back_home(app)
    if not app.game_utils.wait_for_label(base_labels.home_shop_btn):
        raise TimeoutError("Timeout waiting for [home:shop] to appear.")
    app.game_utils.click_on_label(base_labels.home_shop_btn)
    app.game_utils.wait_location_update(GamePageTypes.HOME_TAB.SHOP)

def goto__contest_page(app: "AppProcessor"):
    """ 进入竞技场页面 """
    _goto_tab_contest(app)
    app.game_utils.click_button("コンテスト")  # 点击进入竞技场功能
    app.game_utils.wait_location_update(GamePageTypes.CONTEST_TAB.ARENA)

def goto__claim_task_rewards_page(app: "AppProcessor"):
    """ 进入任务奖励领取页面 """
    _back_home(app)
    if not app.game_utils.wait_for_label(base_labels.home_daily_task):
        raise TimeoutError("Timeout waiting for [home:daily_task] to appear.")
    app.game_utils.click_on_label(base_labels.home_daily_task)
    app.game_utils.wait_location_update(GamePageTypes.HOME_TAB.TASK)