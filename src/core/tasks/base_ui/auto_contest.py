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
from src.entity.Game.Components.Button import ButtonList
from src.entity.Game.Components.CheckBox import CheckBox
from src.entity.Game.Components.Contest import ContestList, ContestItem
from src.utils.debug_tools import DebugTools
from src.utils.logger import logger
from src.utils.string_tools import MatchConfig

if TYPE_CHECKING:
    from src.main import AppProcessor

debug_tools = DebugTools()

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
    if app.config_service().task__auto_contest.auto_reconfigure_team_before_challenge.value:
        _auto_form_team(app)
    while True:
        contest: ContestList | None = None
        for i in range(3):
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
                cv2.imwrite(os.path.join(DebugPath.NotEnoughContests, f"contest_area__{i}.png"), contest.contest_area)
                for index, item in enumerate(contest.contests):
                    cv2.imwrite(os.path.join(DebugPath.NotEnoughContests, f"contest_item__{i}_{index}.png"), item.frame)
            except Exception as e:
                logger.warning(f"Save NotEnoughContests debug image error: {e}")
            sleep(1)
            debug_tools.clear_all()
        if not contest or len(contest) != 3:
            logger.info("There is no contest.")
            break
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

def _start_battle(app: "AppProcessor", width: int, height: int):
    """
    发起挑战并跳过战斗过程。
    若勾选框未启用，自动勾选“跳过”。
    重复点击直到跳过按钮消失。
    """
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
            app.game_utils.click_on_label(BaseUILabels.SKIP_BUTTON)
            sleep(1)
        except Exception as e:
            logger.error(f"not find checkbox: {e}")
    while app.latest_results.exists_label(BaseUILabels.SKIP_BUTTON):
        app.game_utils.click_on_label(BaseUILabels.SKIP_BUTTON)
        sleep(1)
    app.device.click(width // 2, height // 2)


def _finish_battle(app: "AppProcessor"):
    """
    处理战斗结束的按钮点击与奖励弹窗。
    超时等待过程中持续点击屏幕中部。
    """
    COUNT, WAIT = 0, 15
    while COUNT < WAIT:
        buttons = ButtonList(app.latest_results)
        if button := buttons.get_button_by_text(ButtonText.NEXT):
            app.device.click_element(button)
            break
        app.device.click(app.latest_frame.shape[1] // 2, app.latest_frame.shape[0] // 2)
        sleep(1)
        COUNT += 1
    if COUNT >= WAIT:
        raise TimeoutError("Waiting for the challenge to end timeout")
    app.game_utils.click_button(ButtonText.EXIT)
    while True:
        if app.latest_results.exists_label(BaseUILabels.BACK_BTN):
            return
        if app.latest_results.exists_label(BaseUILabels.MODAL_HEADER):
            modal = app.game_utils.wait_for_modal(ModalText.TITLE.RATE_REWARD, no_body=True)
            if modal is None:
                continue
            app.device.click_element(modal.cancel_button)