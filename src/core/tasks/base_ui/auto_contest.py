import os
import random
import traceback
from time import sleep
from typing import TYPE_CHECKING

import cv2

from src.constants.game.text.button_text import ButtonText
from src.constants.game.text.modal_text import ModalText
from src.constants.path.debug_path import DebugPath
from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.entity.Game.Page.Types.index import GamePageTypes
from src.entity.Game.Components.Button import ButtonList
from src.entity.Game.Components.CheckBox import CheckBox
from src.entity.Game.Components.Contest import ContestList, ContestItem
from src.utils.debug_tools import DebugTools
from src.utils.logger import logger
from src.utils.string_tools import MatchConfig, string_match

if TYPE_CHECKING:
    from src.main import AppProcessor

debug_tools = DebugTools()


def _is_contest_detail_page(app: "AppProcessor") -> bool:
    """
    判断是否处于已选对手的详情页（存在“挑战开始”按钮）。
    该页面与竞技场列表页同属 ARENA，需额外识别避免误判。
    """
    if not app.latest_results.exists_label(BaseUILabels.BUTTON):
        return False
    buttons = ButtonList(app.latest_results)
    return buttons.get_button_by_text(
        ButtonText.START_CHALLENGE,
        match_config=MatchConfig(fuzz_threshold=85),
    ) is not None


def _try_back_to_contest_list(app: "AppProcessor") -> bool:
    """尝试从详情页返回竞技场列表页。"""
    back_button = app.latest_results.filter_by_label(BaseUILabels.BACK_BTN).first()
    if back_button is None:
        return False
    app.device.click_element(back_button)
    sleep(1)
    return True

def action__check_and_collect_rewards(app: "AppProcessor"):
    """
    检查并领取上赛季奖励。
    奖励出现时通常位于屏幕下半部，通过点击领取。
    """
    height, width = app.latest_frame.shape[:2]
    items = app.latest_results.filter_by_label(BaseUILabels.ITEM)
    if not items:
        return
    items_cx, items_cy = items.get_COL()
    if items and (height // 2) < items_cy:
        app.device.click(items_cx, items_cy)
        sleep(2)
        app.device.click(items_cx, items_cy)
        logger.info("Last season's rewards have been claimed.")
        sleep(2)

def action__loop_challenge_contest(app: "AppProcessor"):
    """
    持续挑战竞技场，直到没有可挑战对象为止。
    """
    height, width = app.latest_frame.shape[:2]
    empty_retry_count = 0
    if app.config_service().task__auto_contest.auto_reconfigure_team_before_challenge.value:
        _auto_form_team(app)
    while True:
        if _is_contest_detail_page(app):
            logger.warning("Contest detail page detected before list scan, going back to contest list.")
            if _try_back_to_contest_list(app):
                continue

        contest: ContestList | None = None
        for i in range(5):
            try:
                contest = ContestList(app.latest_results, app.latest_frame)
            except Exception as e:
                tb_str = ''.join(traceback.format_exception(type(e), e, e.__traceback__)).rstrip()
                logger.error(tb_str)
                sleep(1)
                continue
            logger.debug(contest)
            if contest and len(contest) == 3:
                debug_tools.clear_all()
                break
            os.makedirs(DebugPath.NotEnoughContests, exist_ok=True)
            try:
                cv2.imwrite(os.path.join(DebugPath.NotEnoughContests, f"full_frame__{i}.png"), app.latest_frame)
                if contest is not None and contest.contest_area is not None and contest.contest_area.size > 0:
                    cv2.imwrite(os.path.join(DebugPath.NotEnoughContests, f"contest_area__{i}.png"), contest.contest_area)
                if contest is not None:
                    for index, item in enumerate(contest.contests):
                        cv2.imwrite(os.path.join(DebugPath.NotEnoughContests, f"contest_item__{i}_{index}.png"), item.frame)
            except Exception as e:
                logger.warning(f"Save NotEnoughContests debug image error: {e}")
            sleep(1)
            debug_tools.clear_all()
        if not contest or len(contest) != 3:
            if contest is not None and contest.is_exhausted:
                logger.info("Contest opportunities are exhausted.")
                break

            current_location = app.game_utils.update_current_location()
            if current_location != GamePageTypes.CONTEST_TAB.ARENA:
                logger.warning(f"Current location is {current_location}, trying to return to contest arena.")
                from src.core.tasks.base_ui.goto_pages import goto__contest_page

                goto__contest_page(app)
                sleep(1)
                continue

            if empty_retry_count < 1:
                empty_retry_count += 1
                logger.warning("Contest list is empty on arena page, retrying once.")
                sleep(1)
                continue

            logger.info("There is no contest.")
            break

        empty_retry_count = 0
        target: ContestItem
        match app.config_service().task__auto_contest.challenge_order.value:
            case "highest_power":
                target = contest.get_combat_power_max()
            case "lowest_power":
                target = contest.get_combat_power_min()
            case "balanced_power":
                avg_power = sum(c.combat_power for c in contest.contests) / len(contest.contests)
                target = min(contest.contests, key=lambda x: abs(x.combat_power - avg_power))
            case "random":
                target = random.choice(contest.contests)
            case _:
                target = random.choice(contest.contests)
        if target is None:
            logger.warning("No valid contest target from strategy, fallback to random choice.")
            target = random.choice(contest.contests)
        logger.info(f"try contest: {target}")
        app.device.click_element(target)
        sleep(1)
        if app.latest_results.exists_label(BaseUILabels.BLANK_SLOT):
            _auto_form_team(app)
        _start_battle(app, width, height)
        _finish_battle(app)

def _auto_form_team(app: "AppProcessor"):
    """
    如果有空的编队槽位，执行自动编队。
    依次点击：编成 -> おまかせ -> 決定 -> 閉じる。
    """
    app.game_utils.click_button(ButtonText.UNIT_FORMATION)
    sleep(1)
    app.game_utils.click_button(ButtonText.AUTO_SELECT)
    sleep(1)
    app.game_utils.click_button(ButtonText.CONFIRM)
    sleep(0.5)
    app.game_utils.click_button(ButtonText.CLOSE)
    app.game_utils.back_next_page()


def _click_skip_until_disappears(
    app: "AppProcessor",
    timeout: float = 20.0,
    interval: float = 0.5,
    stable_missing: int = 3,
):
    """
    持续点击 Skip，直到连续多帧都确认它已经消失。
    避免因为单帧漏检而过早进入结算阶段。
    """
    wait_time = 0.0
    missing_count = 0
    while wait_time < timeout:
        skip_buttons = app.latest_results.filter_by_label(BaseUILabels.SKIP_BUTTON)
        if skip_buttons:
            missing_count = 0
            logger.debug("Found label 'Skip Button', clicking...")
            app.device.click_element(skip_buttons.first())
        else:
            missing_count += 1
            logger.debug(f"Skip Button not found. Stable miss count: {missing_count}/{stable_missing}")
            if missing_count >= stable_missing:
                logger.debug("Skip Button disappeared stably. Entering finish phase.")
                return
        sleep(interval)
        wait_time += interval
    raise TimeoutError("Waiting for skip button to disappear timeout")

def _start_battle(app: "AppProcessor", width: int, height: int):
    """
    发起挑战并跳过战斗过程。
    若勾选框未启用，自动勾选“跳过”。
    若弹出メモリー未編成模态框，自动取消、编队后重试。
    重复点击直到跳过按钮消失。
    """
    start_button = app.game_utils.wait_button(ButtonText.START_CHALLENGE, match_config=MatchConfig(fuzz_threshold=90))
    app.device.click_element(start_button)
    app.game_utils.wait_loading()
    app.game_utils.check_image_change_at_yolobox(start_button)

    # 检查是否弹出メモリー未編成模态框
    modal = app.game_utils.try_get_modal(no_body=True)
    if modal is not None and string_match(
        modal.modal_title,
        ModalText.TITLE.MEMORY_UNASSIGNED,
        MatchConfig(fuzz_threshold=80),
    ):
        logger.info("Memory unassigned modal detected. Cancelling and auto-forming team.")
        if modal.cancel_button is not None:
            app.device.click_element(modal.cancel_button)
        else:
            app.device.click_element(modal.confirm_button)
        sleep(1)
        _auto_form_team(app)
        # 重新发起挑战
        start_button = app.game_utils.wait_button(ButtonText.START_CHALLENGE, match_config=MatchConfig(fuzz_threshold=90))
        app.device.click_element(start_button)
        app.game_utils.wait_loading()
        app.game_utils.check_image_change_at_yolobox(start_button)

    if not app.game_utils.wait_for_label(BaseUILabels.CHECKBOX, interval=0.5, continuous=3, timeout=10):
        logger.error("not find checkbox")
    else:
        try:
            check_box = CheckBox(app.latest_results.filter_by_label(BaseUILabels.CHECKBOX).first())
            if not check_box.checked:
                app.device.click_element(check_box)
        except Exception as e:
            logger.error(f"not find checkbox: {e}")
    _click_skip_until_disappears(app)
    app.device.click(width // 2, height // 2)
    sleep(1)


def _finish_battle(app: "AppProcessor"):
    """
    处理战斗结束的按钮点击与奖励弹窗。
    点击过结算按钮后进入短暂静默等待，避免误触进入详情页。
    """
    COUNT, WAIT = 0, 30
    post_exit_cooldown = 0
    fallback_center_tap_budget = 3
    unknown_location_wait_count = 0
    while COUNT < WAIT:
        skip_buttons = app.latest_results.filter_by_label(BaseUILabels.SKIP_BUTTON)
        if skip_buttons:
            logger.debug("Skip Button still visible during finish phase, clicking again.")
            app.device.click_element(skip_buttons.first())
            sleep(1)
            COUNT += 1
            continue
        if app.latest_results.exists_label(BaseUILabels.BACK_BTN):
            update_location = getattr(app.game_utils, "update_current_location", None)
            if update_location is None or update_location() == GamePageTypes.CONTEST_TAB.ARENA:
                if _is_contest_detail_page(app):
                    logger.debug("Contest detail page detected in finish phase, clicking back.")
                    if _try_back_to_contest_list(app):
                        COUNT += 1
                        continue
                return
        if close_buttons := app.latest_results.filter_by_label(BaseUILabels.CLOSE_BUTTON):
            logger.debug("Found Close Button during finish phase, clicking...")
            app.device.click_element(close_buttons.first())
            post_exit_cooldown = 2
            sleep(1)
            COUNT += 1
            continue
        try_get_modal = getattr(app.game_utils, "try_get_modal", None)
        modal = try_get_modal(no_body=True) if callable(try_get_modal) else None
        if modal is not None:
            if string_match(modal.modal_title, ModalText.TITLE.RATE_REWARD, MatchConfig(fuzz_threshold=90)):
                close_button = modal.cancel_button or modal.confirm_button
                if close_button is not None:
                    app.device.click_element(close_button)
                    post_exit_cooldown = 2
                    sleep(1)
                    COUNT += 1
                    continue
        if app.latest_results.exists_label(BaseUILabels.BUTTON):
            buttons = ButtonList(app.latest_results)
            if button := buttons.get_button_by_text(ButtonText.CLOSE):
                app.device.click_element(button)
                post_exit_cooldown = 2
                sleep(1)
                COUNT += 1
                continue
            if button := buttons.get_button_by_text(ButtonText.NEXT):
                app.device.click_element(button)
                post_exit_cooldown = 2
                sleep(1)
                COUNT += 1
                continue
            if button := buttons.get_button_by_text(ButtonText.EXIT):
                app.device.click_element(button)
                post_exit_cooldown = 2
                sleep(1)
                COUNT += 1
                continue

        # 主路径：即使 BACK_BTN 单帧漏检，也避免在 ARENA 页面误点中部进入详情页。
        update_location = getattr(app.game_utils, "update_current_location", None)
        current_location = update_location() if callable(update_location) else None
        if current_location == GamePageTypes.CONTEST_TAB.ARENA:
            if _is_contest_detail_page(app):
                logger.debug("Contest detail page detected without BACK label, clicking back.")
                if _try_back_to_contest_list(app):
                    COUNT += 1
                    continue
            return

        if post_exit_cooldown > 0:
            logger.debug("Post-exit cooldown active, waiting without center tap.")
            post_exit_cooldown -= 1
            sleep(1)
            COUNT += 1
            continue

        if current_location is None:
            unknown_location_wait_count += 1
            logger.debug("Location unknown in finish phase, waiting without center tap.")
            if unknown_location_wait_count >= 3:
                logger.warning("Finish phase location remains unknown, exit conservatively.")
                return
            sleep(1)
            COUNT += 1
            continue

        unknown_location_wait_count = 0
        if fallback_center_tap_budget <= 0:
            logger.warning(f"No actionable controls on location {current_location}, stop fallback tapping.")
            return

        app.device.click(app.latest_frame.shape[1] // 2, app.latest_frame.shape[0] // 2)
        fallback_center_tap_budget -= 1
        sleep(1)
        COUNT += 1
    logger.warning("Waiting for the challenge to end timeout, exit finish phase conservatively.")
