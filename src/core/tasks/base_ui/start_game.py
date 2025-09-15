from typing import TYPE_CHECKING
from time import sleep

from src.constants.text.modal_text import ModalText
from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.utils.game_tools import get_modal
from src.utils.logger import logger

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
    logger.debug(modal)
    if ModalText.TITLE.CONNECTION_ERROR in modal.modal_title:
        # Token失效
        if ModalText.BODY.CONNECTION_ERROR_BODY.TOKEN_FAIL in modal.modal_body_text:
            logger.warning("Network connection error: Token fail")
            app.device.click_element(modal.cancel_button)
            action__click_start_game(app)
        # 连接超时
        elif ModalText.BODY.CONNECTION_ERROR_BODY.TIMEOUT in modal.modal_body_text:
            logger.warning("Network connection error: Timeout")
            app.device.click_element(modal.confirm_button)
        else:
            logger.warning("Network connection error: Connection error")
            app.device.click_element(modal.confirm_button)
    # 下载新数据
    elif ModalText.TITLE.DATA_DOWNLOAD in modal.modal_title:
        logger.warning("game requires downloading new data.")
        app.device.click_element(modal.confirm_button)
    elif ModalText.TITLE.INIT_ERROR in modal.modal_title:
        logger.error("Game initialization failed.")
        app.device.click_element(modal.cancel_button)
        action__click_start_game(app)
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