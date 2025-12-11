from time import sleep
from typing import TYPE_CHECKING

from src.constants.game.text.modal_text import ModalText
from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.entity.Game.Components.Button import Button
from src.entity.Game.Components.TabBar import TabBar, TabBarItem
from src.utils.logger import logger

if TYPE_CHECKING:
    from src.main import AppProcessor


def claim_task_rewards(app: "AppProcessor"):
    tab_bar = _get_tab_bar(app)
    for tab in tab_bar:
        _process_single_tab(app, tab)
        sleep(1)

def _get_tab_bar(app: "AppProcessor") -> TabBar:
    """
    获取任务页面中的标签栏（tab bar）。
    """
    tab_bar_elem = app.latest_results.filter_by_label(BaseUILabels.TAB_BAR).first()
    return TabBar(tab_bar_elem)


def _process_single_tab(app: "AppProcessor", tab_item: TabBarItem):
    """
    点击 tab 并处理其对应的任务奖励。
    """
    app.device.click_element(tab_item)
    sleep(3)
    button = _get_centered_enabled_button(app)

    if button:
        _claim_reward(app, tab_item, button)
    else:
        logger.info(f"{tab_item.text} has no task rewards to be claimed")


def _get_centered_enabled_button(app: "AppProcessor"):
    """
    获取屏幕中央可点击的按钮。
    """
    buttons = app.latest_results.filter_by_label(BaseUILabels.BUTTON)
    height, width = app.latest_frame.shape[:2]
    frame_cx = width // 2

    for btn in buttons:
        if frame_cx - 10 < btn.cx < frame_cx + 10 and not Button(btn).is_disabled():
            return btn
    return None


def _claim_reward(app: "AppProcessor", tab: TabBarItem, button: Button):
    """
    点击领奖按钮并处理领奖成功的弹窗。
    """
    app.device.click_element(button)
    modal = app.game_utils.wait_for_modal(ModalText.TITLE.RECEIPT_COMPLETED, no_body=True, timeout=10)
    app.device.click_element(modal.cancel_button)
    app.game_utils.click_on_label(BaseUILabels.CLOSE_BUTTON)
    logger.info(f"The task reward of {tab.text} has been claimed")