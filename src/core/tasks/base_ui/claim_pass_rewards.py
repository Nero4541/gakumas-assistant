from copy import copy
from time import sleep
from typing import TYPE_CHECKING, Optional
from skimage.metrics import structural_similarity as ssim

import cv2
import numpy as np

from src.constants.game.text.button_text import ButtonText
from src.constants.game.text.modal_text import ModalText
from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.core.device.Android.app import Android_App
from src.entity.Game.Components.Button import ButtonList
from src.utils.game_tools import get_modal
from src.utils.string_tools import string_match, MatchConfig

if TYPE_CHECKING:
    from src.main import AppProcessor

def claim_pass_rewards(app: "AppProcessor"):
    prev_page: Optional[np.ndarray] = None

    while True:
        app.game_utils.wait_frame_stable(0.9, 1)

        _collect_visible_rewards(app)
        _scroll_reward_list(app)

        app.game_utils.wait_frame_stable()

        if prev_page is not None and _is_page_unchanged(prev_page, app.latest_frame):
            break

        prev_page = copy(app.latest_frame)

def _collect_visible_rewards(app: "AppProcessor"):
    """
    查找并领取当前页奖励
    :param app: app实例
    :return:
    """
    buttons = _find_collect_buttons(app)

    for button in buttons:
        if button.is_disabled():
            continue

        app.device.click_element(button)
        _handle_collect_modal(app)
        app.game_utils.wait_for_label(BaseUILabels.CURRENT_LOCATION)
        sleep(1)

def _find_collect_buttons(app: "AppProcessor") -> list:
    """
    查找“领取”按钮
    :param app: app实例
    :return:
    """
    buttons = ButtonList(app.latest_results)
    return [
        btn for btn in buttons
        if string_match(
            btn.text,
            ButtonText.COLLECT,
            MatchConfig(fuzz_threshold=90)
        )
    ]

def _handle_collect_modal(app: "AppProcessor", max_wait: int = 5):
    """
    处理领取后的弹窗
    :param app: app实例
    :param max_wait: 最长等待时间
    :return:
    """
    for i in range(max_wait + 1):
        if i > max_wait:
            raise TimeoutError("Timeout waiting for modal to appear.")

        if app.latest_results.exists_all_labels(
                [BaseUILabels.BUTTON, BaseUILabels.MODAL_HEADER]
        ):
            modal = get_modal(app.latest_results, True)

            if string_match(modal.modal_title, ModalText.TITLE.RECEIPT_COMPLETED):
                app.device.click_element(modal.cancel_button)
                return

            if string_match(modal.modal_title, ModalText.TITLE.CONNECTION_ERROR):
                app.device.click_element(modal.confirm_button)
            else:
                app.device.click_element(modal.cancel_button)

        sleep(1)

def _scroll_reward_list(app: "AppProcessor"):
    """
    滑动列表
    :param app: app实例
    :return:
    """
    if isinstance(app.device, Android_App):
        buttons = _find_collect_buttons(app)
        if not buttons:
            return

        h_list = [btn.h for btn in buttons]
        width, _ = app.device.get_window_size()
        app.device.swipe(
            width // 2,
            max(h_list),
            width // 2,
            min(h_list),
            0.8
        )
        sleep(0.5)
    else:
        y, x = app.latest_results.frame.shape[:2]
        app.device.scrollY(x // 2, y // 2, -20)

def _is_page_unchanged(prev: np.ndarray, curr: np.ndarray, threshold: float = 0.9) -> bool:
    """
    判断是否翻到尽头
    :param prev: 上一帧
    :param curr: 当前帧
    :param threshold: 阈值
    :return:
    """
    prev_gray = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
    curr_gray = cv2.cvtColor(curr, cv2.COLOR_BGR2GRAY)
    score, _ = ssim(prev_gray, curr_gray, full=True)
    return score > threshold
