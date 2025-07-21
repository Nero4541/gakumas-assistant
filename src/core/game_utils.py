from time import sleep
from typing import TYPE_CHECKING, Optional

from src.entity.Game.Components.Button import ButtonList
from src.entity.Game.Components.Modal import Modal
from src.entity.Game.Page.Types.index import GamePageTypes
from src.utils.game_tools import get_current_location
from src.utils.logger import logger
from src.constants import *
from src.utils.string_tools import string_match, MatchConfig
from src.utils.yolo_tools import get_modal

if TYPE_CHECKING:
    from app import AppProcessor

class GameUtils:
    _app_processor: "AppProcessor"

    def __init__(self, app_processor: "AppProcessor"):
        self._app_processor = app_processor

    def wait_for_label(self, label, timeout=30, interval=1, continuous=1):
        """
        等待指定标签的框出现
        :param label: 标签
        :param timeout: 超时时间
        :param interval: 轮询间隔
        :param continuous: 连续出现几次再返回
        :return:
        """
        WAIT_TIME = 0
        COUNT = 0
        logger.debug(f"waiting for label: {label} (timeout={timeout}, interval={interval}, continuous={continuous})")
        while WAIT_TIME <= timeout:
            if COUNT > continuous:
                logger.debug(f"Label '{label}' appeared {continuous} times. Returning True.")
                return True
            if self._app_processor.latest_results.filter_by_label(label):
                COUNT += 1
                logger.debug(f"Found label '{label}' (count={COUNT})")
                sleep(0.3)
                continue
            else:
                COUNT = 0
                logger.debug(f"Label '{label}' not found. Resetting count.")
            sleep(interval)
            WAIT_TIME += interval
            logger.debug(f"Waiting... {WAIT_TIME}/{timeout}s")
        logger.warning(f"Timeout reached ({timeout}s): Label '{label}' not found.")
        return False

    def wait_for_modal(self, modal_title, timeout=30, interval=1, no_body: bool = False, match_config: MatchConfig = None) -> Optional[Modal]:
        """
        等待指定标题的模态框出现
        :param modal_title: 模态框标题
        :param timeout: 超时时间
        :param interval: 轮询间隔
        :param no_body: 不需要框体文本
        :param match_config: 匹配配置
        :return:
        """
        logger.debug(f"Waiting for modal with title: {modal_title} (timeout={timeout}, interval={interval}, no_body={no_body})")
        wait_time = 0
        match_config = match_config if match_config is not None else MatchConfig(fuzz_threshold=80)
        while wait_time < timeout:
            headers = self._app_processor.latest_results.filter_by_label(base_labels.modal_header)
            buttons = self._app_processor.latest_results.filter_by_label(base_labels.button)

            if not (headers and buttons):
                logger.debug(f"No modal header or button found, waiting... ({wait_time}/{timeout})")
            else:
                modal = get_modal(self._app_processor.latest_results, self._app_processor.latest_frame, no_body)
                if modal:
                    if modal_title is None or string_match(modal.modal_title, modal_title, match_config):
                        logger.debug(f"Modal found: {modal.modal_title}")
                        return modal
                    else:
                        logger.debug(f"Modal title '{modal.modal_title}' does not match '{modal_title}'")

            sleep(interval)
            wait_time += interval
            logger.debug(f"Waiting... {wait_time}/{timeout}s")

        logger.warning(f"Timeout reached ({timeout}s): Modal with title '{modal_title}' not found.")
        return None

    def click_on_label(self, label, timeout=10, interval=1):
        """
        等待指定标签并点击
        :param label: 标签
        :param timeout: 超时时间
        :param interval: 轮询间隔
        :return:
        """
        WAIT_TIME = 0
        COUNT = 0
        logger.debug(f"waiting to click label: {label} (timeout={timeout}, interval={interval})")
        while WAIT_TIME < timeout:
            boxs = self._app_processor.latest_results.filter_by_label(label)
            if boxs:
                logger.debug(f"Found label '{label}', clicking...")
                self._app_processor.app.click_element(boxs.first())
                return True
            else:
                COUNT += 1
                if COUNT >= 3:
                    logger.warning(f"Label '{label}' not found 3 times, breaking out of loop.")
                    break
                sleep(interval)
                logger.debug(f"Label '{label}' not found, retrying... ({WAIT_TIME}/{timeout}s)")
            WAIT_TIME += interval
        logger.warning(f"Timeout reached ({timeout}s): Label '{label}' not found.")
        return False
    
    def wait_loading(self, timeout=60):
        """
        等待加载
        :param timeout: 超时时间
        :return:
        """
        WAIT_TIME = 0
        COUNT = 0
        sleep(1)
        logger.debug("Waiting for loading")
        while WAIT_TIME < timeout:
            if self._app_processor.latest_results.filter_by_labels([base_labels.general_loading1, base_labels.general_loading2]):
                sleep(1)
                WAIT_TIME += 1
            else:
                if COUNT > 3:
                    logger.debug("Wait for the loading to finish")
                    return True
                else:
                    COUNT += 1
                    sleep(0.3)
        raise TimeoutError("Waiting for a load timeout")

    def click_button(self, text, timeout=10, match_config: MatchConfig = MatchConfig(use_fuzz=True, fuzz_threshold=0.7)):
        """
        点击指定文本按钮
        :param match_config:
        :param text: 按钮文本
        :param timeout: 超时时间
        :return:
        """
        logger.debug(f"waiting click label: {text}")
        self._app_processor.app.click_element(self.wait_button(text,timeout, match_config))

    def wait_button(self, text, timeout=10, match_config: MatchConfig = MatchConfig(use_fuzz=True, fuzz_threshold=0.7)):
        """
        等待指定文本按钮
        :param match_config:
        :param text: 按钮文本
        :param timeout: 超时时间
        :return:
        """
        COUNT = 0
        while COUNT < timeout:
            buttons = ButtonList(self._app_processor.latest_results)
            logger.debug(buttons)
            if button := buttons.get_button_by_text(text, match_config):
                return button
            sleep(1)
            COUNT += 1
        raise TimeoutError(f"Waiting for {text} button timeout")

    def go_home(self, max_try: int = 5):
        """
        返回主页
        :return:
        """
        self.update_current_location()
        if self._app_processor.game_status_manager.current_location == GamePageTypes.MAIN_MENU__HOME:
            return
        for _ in range(max_try):
            logger.debug(f"[{max_try}/{_}]Try going home")
            main_menu_items = [
                value for name, value in vars(GamePageTypes).items()
                if name.startswith("MAIN_MENU__")
            ]
            if self.update_current_location() in main_menu_items:
                self._app_processor.app.click_element(self._app_processor.latest_results.filter_by_label(base_labels.tab_home).first())
                self.wait_loading()
                self.update_current_location()
                return
            elif go_home_btn := self._app_processor.latest_results.filter_by_label(base_labels.go_home_btn):
                self._app_processor.app.click_element(go_home_btn.first())
                self.wait_loading()
                self.update_current_location()
                return
            sleep(1)
        raise RuntimeError("Going home failed")


    def back_next_page(self):
        """
        返回上一页
        :return:
        """
        logger.debug("Going back next page")
        if self.wait_for_label(base_labels.back_btn, 3):
            self._app_processor.app.click_element(self._app_processor.latest_results.filter_by_label(base_labels.back_btn).first())
        else:
            raise TimeoutError("Waiting for a back button timeout")

    def update_current_location(self, new_location: str = None):
        """
        更细游戏管理器中的当前位置
        :param new_location: 可选，直接按输入的位置
        :return:
        """
        logger.debug("Updating current location......")
        update = False
        if new_location and new_location != self._app_processor.game_status_manager.current_location:
            update = True
            self._app_processor.game_status_manager.current_location = new_location
        else:
            current_location = get_current_location(self._app_processor.latest_results)
            if current_location and current_location != self._app_processor.game_status_manager.current_location:
                update = True
                self._app_processor.game_status_manager.current_location = current_location
        if update: logger.debug(f"Current location: {self._app_processor.game_status_manager.current_location}")
        return self._app_processor.game_status_manager.current_location

    def wait_location_update(self, target_location: str, timeout=10):
        """
        等待当前位置刷新
        :param target_location: 目标位置
        :param timeout: 超时时间
        :return:
        """
        logger.debug(f"Wait for the location to be updated to {target_location}......")
        COUNT = 0
        while True:
            if COUNT > timeout:
                raise TimeoutError("Timeout for waiting for location update")
            if self.update_current_location() == target_location:
                return True
            else:
                COUNT += 1
                sleep(1)