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
from src.utils.task_debug_tools import record_task_step
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
            if _is_contest_detail_page(app):
                logger.debug("Contest detail page detected during retry loop, breaking early.")
                break
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
    # 处理所有对战Stage（竞技场通常有3个Stage）
    for stage_round in range(5):
        _click_skip_until_disappears(app)
        app.device.click(width // 2, height // 2)
        sleep(1)

        # 检查是否有「対戦開始」按钮（多Stage模式的继续按钮）
        battle_btn = _try_find_battle_start_button(app)
        if battle_btn is None:
            logger.debug(f"No 対戦開始 button found after round {stage_round + 1}, all stages complete")
            break
        logger.info(f"Multi-stage contest: clicking 対戦開始 for remaining stages (round {stage_round + 1})")
        app.device.click_element(battle_btn)
        sleep(1)


def _try_find_battle_start_button(app: "AppProcessor", retries: int = 3, interval: float = 0.5):
    """
    在多Stage对战概览画面寻找「対戦開始」按钮。
    因为画面过渡可能有延迟，会重试几次。
    """
    for i in range(retries):
        buttons = ButtonList(app.latest_results)
        btn = buttons.get_button_by_text(
            ButtonText.BATTLE_START,
            match_config=MatchConfig(fuzz_threshold=85),
        )
        if btn is not None:
            return btn
        sleep(interval)
    return None


def _finish_battle(app: "AppProcessor"):
    """
    处理战斗结束的按钮点击与奖励弹窗。
    分阶段处理：
    1. 持续点击屏幕中心，等待"次へ"按钮出现并点击
    2. 持续推进结算页（优先点"次へ"/"終了"，OCR 失败时兜底点底部主按钮）
    3. 等待返回竞技场页面，同时处理可能出现的奖励模态框
    """
    # 阶段1: 持续点击屏幕中心，等待"次へ"按钮出现
    count = 0
    max_phase1_attempts = 60
    while count < max_phase1_attempts:
        buttons = ButtonList(app.latest_results)
        if button := buttons.get_button_by_text(ButtonText.NEXT):
            logger.debug("Found NEXT button, clicking.")
            record_task_step(app, "auto_contest.finish.phase1.click_next", attempts=count)
            app.device.click_element(button)
            sleep(1)
            break
        # 安全兜底：如果仍有「対戦開始」按钮，说明多Stage还没打完
        if button := buttons.get_button_by_text(
            ButtonText.BATTLE_START,
            match_config=MatchConfig(fuzz_threshold=85),
        ):
            logger.info("Found 対戦開始 in finish phase, clicking to continue remaining stages")
            record_task_step(app, "auto_contest.finish.phase1.click_battle_start", attempts=count)
            app.device.click_element(button)
            sleep(1)
            _click_skip_until_disappears(app)
            app.device.click(app.latest_frame.shape[1] // 2, app.latest_frame.shape[0] // 2)
            sleep(1)
            count = 0
            continue
        if count == 0 or count % 10 == 0:
            record_task_step(app, "auto_contest.finish.phase1.wait_next", attempts=count)
        app.device.click(app.latest_frame.shape[1] // 2, app.latest_frame.shape[0] // 2)
        sleep(1)
        count += 1

    # 阶段2/3: 推进结算页并等待返回竞技场页面，处理可能出现的奖励模态框
    idle_count = 0
    while True:
        if app.latest_results.exists_label(BaseUILabels.BACK_BTN):
            if _is_contest_detail_page(app):
                record_task_step(app, "auto_contest.finish.return_to_contest_list")
                _try_back_to_contest_list(app)
                sleep(1)
                continue
            record_task_step(app, "auto_contest.finish.returned_to_arena")
            return
        if app.latest_results.exists_label(BaseUILabels.MODAL_HEADER):
            modal = app.game_utils.wait_for_modal(ModalText.TITLE.RATE_REWARD, no_body=True)
            if modal is not None:
                close_button = modal.cancel_button or modal.confirm_button
                if close_button:
                    record_task_step(
                        app,
                        "auto_contest.finish.close_reward_modal",
                        title=getattr(modal, "modal_title", None),
                    )
                    app.device.click_element(close_button)
                    sleep(1)
                    idle_count = 0
                    continue

        buttons = ButtonList(app.latest_results)
        if button := buttons.get_button_by_text(ButtonText.NEXT):
            logger.debug("Found NEXT button during finish phase, clicking.")
            record_task_step(app, "auto_contest.finish.phase2.click_next")
            app.device.click_element(button)
            sleep(1)
            idle_count = 0
            continue
        if button := buttons.get_button_by_text(ButtonText.EXIT):
            logger.debug("Found EXIT button during finish phase, clicking.")
            record_task_step(app, "auto_contest.finish.phase2.click_exit")
            app.device.click_element(button)
            sleep(1)
            idle_count = 0
            continue
        if button := _get_bottom_primary_button(buttons, app.latest_frame.shape):
            logger.debug(
                f"Found bottom primary button during finish phase, clicking fallback. "
                f"text={button.text!r}"
            )
            record_task_step(
                app,
                "auto_contest.finish.phase2.click_primary_fallback",
                text=button.text,
                cx=int(button.cx),
                cy=int(button.cy),
            )
            app.device.click_element(button)
            sleep(1)
            idle_count = 0
            continue
        idle_count += 1
        if idle_count == 1 or idle_count % 10 == 0:
            record_task_step(
                app,
                "auto_contest.finish.phase2.wait_progress",
                idle_loops=idle_count,
                button_count=len(buttons),
            )
        sleep(1)


def _get_bottom_primary_button(buttons: ButtonList, frame_shape: tuple[int, ...]):
    if not buttons:
        return None

    frame_height, frame_width = frame_shape[:2]
    min_width = int(frame_width * 0.22)
    bottom_threshold = int(frame_height * 0.82)
    center_tolerance = int(frame_width * 0.18)

    candidates = []
    for button in buttons:
        if button is None or button.is_disabled():
            continue
        button_width = int(button.w - button.x)
        if button_width < min_width:
            continue
        if int(button.cy) < bottom_threshold:
            continue
        if abs(int(button.cx) - frame_width // 2) > center_tolerance:
            continue
        candidates.append(button)

    if not candidates:
        return None
    return max(candidates, key=lambda item: (int(item.cy), int(item.w - item.x)))
