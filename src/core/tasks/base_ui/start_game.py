from typing import TYPE_CHECKING

from time import sleep

from src.constants import *
from src.constants.base_ui import labels
from src.entity.Game.Page.Types.index import GamePageTypes
from src.utils.yolo_tools import get_modal
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
def handle__network_error_modal_boxes(app: "AppProcessor"):
    """处理：通信错误模态框"""
    if app.latest_results.filter_by_label(labels.modal_header):
        modal = get_modal(app.latest_results, app.latest_frame)
        if modal_text.connection_error in modal.modal_title:
            # Token失效
            if modal_text.ConnectionError_Body.Token_Fail in modal.modal_body:
                app.app.click_element(modal.cancel_button)
                action__click_start_game(app)
            # 连接超时
            elif modal_text.ConnectionError_Body.Timeout in modal.modal_body:
                app.app.click_element(modal.confirm_button)
        # 下载新数据
        elif modal_text.data_download in modal.modal_title:
            app.app.click_element(modal.confirm_button)
        app.game_utils.wait_loading()
        handle__network_error_modal_boxes(app)

def action__wait_enter_home(app: "AppProcessor"):
    """动作：检查主界面标识是否存在"""
    if app.latest_results.exists_label(labels.tab_home):
        return True
    while True:
        handle__network_error_modal_boxes(app)
        if close_btn := app.latest_results.filter_by_label(labels.close_button):
            app.app.click_element(close_btn.first())
            sleep(1)
        if skip_btn := app.latest_results.filter_by_label(labels.skip_button):
            app.app.click_element(skip_btn.first())
            sleep(1)
        elif app.latest_results.exists_label(labels.tab_home):
            return True
        else:
            height, width = app.latest_frame.shape[:2]
            app.app.click(width // 3, height // 2)
            sleep(1)