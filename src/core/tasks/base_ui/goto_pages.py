from typing import TYPE_CHECKING

from src.constants.game.text.button_text import ButtonText
from src.constants.game.text.modal_text import ModalText
from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.entity.Game.Components.Button import ButtonList
from src.entity.Game.Page.Types.index import GamePageTypes
from src.utils.game_tools import get_modal
from src.utils.string_tools import MatchConfig
from src.utils.task_debug_tools import record_task_step

if TYPE_CHECKING:
    from src.main import AppProcessor


_CONTEST_ENTRY_BUTTON_MATCH = MatchConfig(fuzz_threshold=80, normalize=True)

def _back_home(app: "AppProcessor"):
    if app.game_utils.update_current_location() != GamePageTypes.MAIN_MENU__HOME:
        app.game_utils.go_home()
        try:
            app.game_utils.wait_location_update(GamePageTypes.MAIN_MENU__HOME)
        except TimeoutError:
            from src.core.tasks.base_ui.start_game import action__wait_enter_home

            action__wait_enter_home(app)
            app.game_utils.update_current_location(GamePageTypes.MAIN_MENU__HOME)

def _goto_tab_contest(app: "AppProcessor"):
    if app.game_utils.update_current_location() == GamePageTypes.MAIN_MENU__CONTEST:
        return
    _back_home(app)
    if not app.game_utils.wait_for_label(BaseUILabels.TAB_CONTEST):
        raise TimeoutError("Timeout waiting for [tab:contest] to appear.")
    app.game_utils.click_on_label(BaseUILabels.TAB_CONTEST)
    app.game_utils.wait_location_update(GamePageTypes.MAIN_MENU__CONTEST)

def _goto_tab_idol(app: "AppProcessor"):
    if app.game_utils.update_current_location() == GamePageTypes.MAIN_MENU__IDOL:
        return
    _back_home(app)
    if not app.game_utils.wait_for_label(BaseUILabels.TAB_IDOL):
        raise TimeoutError("Timeout waiting for [tab:idol] to appear.")
    app.game_utils.click_on_label(BaseUILabels.TAB_IDOL)
    app.game_utils.wait_location_update(GamePageTypes.MAIN_MENU__IDOL)

def goto__get_expenditure(app: "AppProcessor", candidate_index: int = 0):
    """ 进入“活动费”领取菜单，点击第 candidate_index 个候选按钮 """
    _back_home(app)
    if not app.game_utils.wait_for_label(BaseUILabels.HOME_GET_EXPENDITURE):
        raise TimeoutError("Timeout waiting for [home:expenditure] to appear.")
    candidates = app.latest_results.filter_by_label(BaseUILabels.HOME_GET_EXPENDITURE)
    if not candidates:
        raise TimeoutError("Failed to locate [home:expenditure] button after label wait.")
    idx = min(candidate_index, len(candidates) - 1)
    expenditure_button = candidates.boxes[idx]
    app.game_utils.click_element_and_wait_trigger(expenditure_button, retries=3, timeout=3.0, interval=0.1)


def goto__work_dispatch_page(app: "AppProcessor"):
    """ 进入任务派遣页面 """
    _back_home(app)
    if not app.game_utils.wait_for_label(BaseUILabels.HOME_DISPATCH_WORK):
        raise TimeoutError("Timeout waiting for [home:dispatch work] to appear.")
    app.game_utils.click_on_label(BaseUILabels.HOME_DISPATCH_WORK)
    app.game_utils.wait_loading()

def goto__gift_page(app: "AppProcessor"):
    """ 进入礼物领取页面 """
    _back_home(app)
    if not app.game_utils.wait_for_label(BaseUILabels.HOME_GIFT_BTN):
        raise TimeoutError("Timeout waiting for [home:gift] to appear.")
    app.game_utils.click_on_label(BaseUILabels.HOME_GIFT_BTN)
    app.game_utils.wait_location_update(GamePageTypes.HOME_TAB.GIFT)

def goto__shop_page(app: "AppProcessor"):
    """ 进入商店页面 """
    _back_home(app)
    if not app.game_utils.wait_for_label(BaseUILabels.HOME_SHOP_BTN):
        raise TimeoutError("Timeout waiting for [home:shop] to appear.")
    app.game_utils.click_on_label(BaseUILabels.HOME_SHOP_BTN)
    app.game_utils.wait_location_update(GamePageTypes.HOME_TAB.SHOP)

def goto__contest_page(app: "AppProcessor"):
    """ 进入竞技场页面 """
    if app.game_utils.update_current_location() == GamePageTypes.CONTEST_TAB.ARENA:
        record_task_step(app, "goto_contest.already_in_arena")
        return
    _goto_tab_contest(app)
    record_task_step(app, "goto_contest.enter_tab")
    if app.game_utils.update_current_location() == GamePageTypes.CONTEST_TAB.ARENA:
        record_task_step(app, "goto_contest.entered_arena_from_tab")
        return

    last_error: TimeoutError | None = None
    for attempt in range(2):
        contest_button = _get_contest_entry_button(app)
        if contest_button is None:
            raise TimeoutError("Timeout waiting for contest entry button to appear.")

        record_task_step(
            app,
            "goto_contest.click_entry",
            attempt=attempt + 1,
            text=getattr(contest_button, "text", None),
            cx=int(contest_button.cx),
            cy=int(contest_button.cy),
        )
        if not app.game_utils.click_element_and_wait_trigger(
                contest_button,
                retries=3,
                timeout=2.5,
                interval=0.1,
        ):
            record_task_step(app, "goto_contest.click_entry_no_trigger", attempt=attempt + 1)
            app.device.click_element(contest_button)

        try:
            app.game_utils.wait_loading(timeout=8)
        except TimeoutError as exc:
            last_error = exc
            record_task_step(
                app,
                "goto_contest.wait_loading_timeout",
                attempt=attempt + 1,
                error=str(exc),
            )

        try:
            app.game_utils.wait_location_update(GamePageTypes.CONTEST_TAB.ARENA, timeout=10)
            record_task_step(app, "goto_contest.entered_arena", attempt=attempt + 1)
            return
        except TimeoutError as exc:
            last_error = exc
            record_task_step(
                app,
                "goto_contest.location_timeout",
                attempt=attempt + 1,
                error=str(exc),
            )
            if app.game_utils.update_current_location() != GamePageTypes.MAIN_MENU__CONTEST:
                continue

    if last_error is not None:
        raise last_error
    raise TimeoutError("Timeout waiting for contest page to open.")


def _get_contest_entry_button(app: "AppProcessor"):
    buttons = ButtonList(app.latest_results)
    if not buttons:
        return None

    if button := buttons.get_button_by_text(
            ButtonText.MAIN_MENU__CONTEST.CONTEST,
            match_config=_CONTEST_ENTRY_BUTTON_MATCH,
    ):
        return button

    frame_height, frame_width = app.latest_frame.shape[:2]
    min_width = int(frame_width * 0.35)
    min_height = int(frame_height * 0.10)
    right_threshold = int(frame_width * 0.58)
    top_threshold = int(frame_height * 0.55)
    bottom_threshold = int(frame_height * 0.88)

    candidates = []
    for button in buttons:
        if button is None or button.is_disabled():
            continue
        button_width = int(button.w - button.x)
        button_height = int(button.h - button.y)
        if button_width < min_width or button_height < min_height:
            continue
        if int(button.cx) < right_threshold:
            continue
        if not top_threshold <= int(button.cy) <= bottom_threshold:
            continue
        candidates.append(button)

    if not candidates:
        return None
    return max(candidates, key=lambda item: (int(item.w - item.x), int(item.cx), int(item.cy)))

def goto__claim_task_rewards_page(app: "AppProcessor"):
    """ 进入任务奖励领取页面 """
    _back_home(app)
    if not app.game_utils.wait_for_label(BaseUILabels.HOME_DAILY_TASK):
        raise TimeoutError("Timeout waiting for [home:daily_task] to appear.")
    app.game_utils.click_on_label(BaseUILabels.HOME_DAILY_TASK)
    app.game_utils.wait_location_update(GamePageTypes.HOME_TAB.TASK)

def goto__claim_pass_rewards(app: "AppProcessor"):
    """ 进入大月卡奖励领取页面 """
    goto__claim_task_rewards_page(app)
    app.game_utils.click_button(ButtonText.PAGE__TASK_REWARDS.PASS_REWARDS, match_config=MatchConfig(fuzz_threshold=90))
    app.game_utils.wait_loading()
    for i in range(3):
        if not app.latest_results.exists_label(BaseUILabels.MODAL_HEADER) and app.latest_results.exists_all_labels([BaseUILabels.CURRENT_LOCATION, BaseUILabels.BUTTON]):
            break
        if app.latest_results.exists_label(BaseUILabels.MODAL_HEADER):
            modal = app.game_utils.wait_for_modal(ModalText.TITLE.INFO_FETCH_FAILED, timeout=5, no_body=True)
            if not modal:
                continue
            app.device.click_element(modal.confirm_button)
            app.game_utils.wait_loading()
            if modal := app.game_utils.wait_for_label(BaseUILabels.MODAL_HEADER, timeout=5):
                app.device.click_element(modal.cancel_button)
            app.game_utils.wait_loading()
    if app.latest_results.exists_label(BaseUILabels.MODAL_HEADER):
        modal = get_modal(app.latest_results, True)
        if modal:
            app.device.click_element(modal.cancel_button)
    app.game_utils.wait_location_update(GamePageTypes.HOME_TAB.PASS_REWARD)

def goto_support_card_list_page(app: "AppProcessor"):
    _goto_tab_idol(app)
    app.game_utils.click_button(ButtonText.PAGE__IDOL.SUPPORT_CARD, match_config=MatchConfig(fuzz_threshold=90))
    app.game_utils.wait_loading()
    app.game_utils.wait_for_label(BaseUILabels.SUPPORT_CARD)

def goto_idol_card_list_page(app: "AppProcessor"):
    """进入 P アイドル育成列表页面"""
    _goto_tab_idol(app)
    app.game_utils.click_button(ButtonText.PAGE__IDOL.IDOL_CULTIVATION, match_config=MatchConfig(fuzz_threshold=85))
    app.game_utils.wait_loading()
    if not app.game_utils.wait_for_label(BaseUILabels.PRODUCT_CARD_SELECTED, timeout=10):
        raise TimeoutError("Timeout waiting for idol card cultivation carousel to appear.")
