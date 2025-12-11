from typing import TYPE_CHECKING
from time import sleep

from src.constants.game.text.modal_text import ModalText
from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.utils.game_tools import get_modal
from src.utils.logger import logger
from src.utils.string_tools import string_match

if TYPE_CHECKING:
    from src.main import AppProcessor

def action__click_start_game(app: "AppProcessor"):
    """动作：点击启动游戏"""
    if app.game_utils.wait_for_label(BaseUILabels.START_MENU_CLICK_CONTINUE_FLAG):
       app.game_utils.click_on_label(BaseUILabels.START_MENU_CLICK_CONTINUE_FLAG)
    else:
        raise TimeoutError("Timeout waiting for continue flag in the start menu.")

def _handle__modal_boxes(app: "AppProcessor"):
    """处理模态框"""
    logger.debug("_handle__modal_boxes")
    modal = get_modal(app.latest_results)
    if string_match(ModalText.TITLE.CONNECTION_ERROR, modal.modal_title):
        # Token失效
        if string_match(ModalText.BODY.CONNECTION_ERROR_ID.TOKEN_FAIL, modal.modal_body_text):
            logger.warning("Network connection error: Token fail")
            app.device.click_element(modal.cancel_button)
            action__click_start_game(app)
        # 连接超时
        elif string_match(ModalText.BODY.CONNECTION_ERROR_ID.TIMEOUT, modal.modal_body_text):
            logger.warning("Network connection error: Timeout")
            app.device.click_element(modal.confirm_button)
        else:
            logger.warning("Network connection error: Connection error")
            app.device.click_element(modal.confirm_button)
    # 下载新数据
    elif string_match(ModalText.TITLE.DATA_DOWNLOAD, modal.modal_title):
        logger.warning("game requires downloading new data.")
        app.device.click_element(modal.confirm_button)
    elif string_match(ModalText.TITLE.INIT_ERROR, modal.modal_title):
        logger.error("Game initialization failed.")
        app.device.click_element(modal.cancel_button)
        action__click_start_game(app)
    # 游戏更新
    elif string_match(ModalText.TITLE.GAME_UPDATE, modal.modal_title):
        raise RuntimeWarning("Game requires an update from the App Store. Please update manually.")
    else:
        raise RuntimeError("Unknown modal box")
    sleep(1)
    app.game_utils.wait_loading()

def action__wait_enter_home(app: "AppProcessor"):
    """动作：检查主界面标识是否存在"""
    while True:
        if close_btn := app.latest_results.filter_by_label(BaseUILabels.CLOSE_BUTTON):
            app.device.click_element(close_btn.first())
            sleep(1)
        elif skip_btn := app.latest_results.filter_by_label(BaseUILabels.SKIP_BUTTON):
            app.device.click_element(skip_btn.first())
            sleep(1)
        elif app.latest_results.filter_by_label(BaseUILabels.MODAL_HEADER):
            _handle__modal_boxes(app)
        elif app.latest_results.filter_by_label(BaseUILabels.TAB_HOME):
            return True
        else:
            height, width = app.latest_frame.shape[:2]
            app.device.click(width // 3, height // 2)
            sleep(1)