from typing import TYPE_CHECKING

from time import sleep

from src.constants import *
from src.constants.base_ui import labels
from src.utils.game_tools import get_modal
from src.utils.logger import logger

if TYPE_CHECKING:
    from src.main import AppProcessor

def action__click_start_game(app: "AppProcessor"):
    """动作：点击启动游戏"""
    if app.game_utils.wait_for_label(labels.start_menu_click_continue_flag):
        if not app.game_utils.click_on_label(labels.start_menu_click_continue_flag):
            raise TimeoutError("Failed to click on the continue flag within the timeout.")
    else:
        raise TimeoutError("Timeout waiting for continue flag in the start menu.")

@logger.catch
def _handle__modal_boxes(app: "AppProcessor"):
    """处理模态框"""
    logger.debug("_handle__modal_boxes")
    modal = get_modal(app.latest_results, app.latest_frame)
    logger.debug(modal)
    if modal_text.connection_error in modal.modal_title:
        # Token失效
        if modal_text.ConnectionError_Body.Token_Fail in modal.modal_body_text:
            logger.warning("Network connection error: Token fail")
            app.app.click_element(modal.cancel_button)
            action__click_start_game(app)
        # 连接超时
        elif modal_text.ConnectionError_Body.Timeout in modal.modal_body_text:
            logger.warning("Network connection error: Timeout")
            app.app.click_element(modal.confirm_button)
        else:
            logger.warning("Network connection error: Connection error")
            app.app.click_element(modal.confirm_button)
    # 下载新数据
    elif modal_text.data_download in modal.modal_title:
        logger.warning("game requires downloading new data.")
        app.app.click_element(modal.confirm_button)
    elif modal_text.init_error in modal.modal_title:
        logger.error("Game initialization failed.")
        app.app.click_element(modal.cancel_button)
        action__click_start_game(app)
    else:
        raise RuntimeError("Unknown modal box")
    sleep(1)
    app.game_utils.wait_loading()

def action__wait_enter_home(app: "AppProcessor"):
    """动作：检查主界面标识是否存在"""
    while True:
        if close_btn := app.latest_results.filter_by_label(labels.close_button):
            app.app.click_element(close_btn.first())
            sleep(1)
        elif skip_btn := app.latest_results.filter_by_label(labels.skip_button):
            app.app.click_element(skip_btn.first())
            sleep(1)
        elif app.latest_results.filter_by_label(labels.modal_header):
            _handle__modal_boxes(app)
        elif app.latest_results.filter_by_label(labels.tab_home):
            return True
        else:
            height, width = app.latest_frame.shape[:2]
            app.app.click(width // 3, height // 2)
            sleep(1)