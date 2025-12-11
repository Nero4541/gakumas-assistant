from copy import copy
from time import sleep, time
from typing import TYPE_CHECKING, Optional

import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim
from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.entity.Game.Components.Button import ButtonList
from src.entity.Game.Components.Modal import Modal
from src.entity.Game.Page.Types.index import GamePageTypes
from src.entity.Yolo import Yolo_Box
from src.utils.debug_tools import DebugTools
from src.utils.game_tools import get_current_location, get_modal
from src.utils.logger import logger
from src.utils.performance_tools import timeit
from src.utils.string_tools import string_match, MatchConfig

if TYPE_CHECKING:
    from src.main import AppProcessor

class GameUtils:
    _app_processor: "AppProcessor"
    debug_tools = DebugTools()

    def __init__(self, app_processor: "AppProcessor"):
        self._app_processor = app_processor

    def wait_for_label(self, label, timeout=15, interval=1, continuous=1):
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
        logger.debug(f"waiting for label: {label}")
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

    def wait_label_exist(self, label, timeout=15, interval=1, continuous=1):
        WAIT_TIME = 0
        COUNT = 0
        logger.debug(f"Waiting label exist: {label}")
        while WAIT_TIME <= timeout:
            if COUNT > continuous:
                logger.debug(f"Label '{label}' appeared {continuous} times. Returning True.")
                return True
            if not self._app_processor.latest_results.filter_by_label(label):
                COUNT += 1
                logger.debug(f"Not found label '{label}' (count={COUNT})")
                sleep(0.3)
                continue
            else:
                COUNT = 0
                logger.debug(f"Label '{label}' found. Resetting count.")
            sleep(interval)
            WAIT_TIME += interval
            logger.debug(f"Waiting... {WAIT_TIME}/{timeout}s")
        logger.warning(f"Timeout reached ({timeout}s): Label '{label}' found.")
        return False

    def wait_for_modal(self, modal_title, timeout=10, interval=1, no_body: bool = False, match_config: MatchConfig = None) -> Optional[Modal]:
        """
        等待指定标题的模态框出现
        :param modal_title: 模态框标题
        :param timeout: 超时时间
        :param interval: 轮询间隔
        :param no_body: 不需要框体文本
        :param match_config: 匹配配置
        :return:
        """
        logger.debug(f"Waiting for modal with title: {modal_title}")
        wait_time = 0
        match_config = match_config if match_config is not None else MatchConfig(fuzz_threshold=80)
        while wait_time < timeout:
            headers = self._app_processor.latest_results.filter_by_label(BaseUILabels.MODAL_HEADER)
            buttons = self._app_processor.latest_results.filter_by_label(BaseUILabels.BUTTON)

            if not (headers and buttons):
                logger.debug(f"No modal header or button found, waiting... ({wait_time}/{timeout})")
            else:
                modal = get_modal(self._app_processor.latest_results, no_body)
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
        logger.debug(f"waiting to click label: {label}")
        while WAIT_TIME < timeout:
            boxs = self._app_processor.latest_results.filter_by_label(label)
            if boxs:
                logger.debug(f"Found label '{label}', clicking...")
                self._app_processor.device.click_element(boxs.first())
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

    def wait_loading(self, timeout=-1):
        """
        等待加载
        :param timeout: 超时时间
        :return:
        """
        WAIT_TIME = 0
        COUNT = 0
        sleep(1)
        while timeout == -1 or WAIT_TIME < timeout:
            if self._app_processor.latest_results.filter_by_labels([BaseUILabels.GENERAL_LOADING1, BaseUILabels.GENERAL_LOADING2]):
                if WAIT_TIME == 0:
                   logger.debug("Waiting for loading")
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

    def check_label_exists_at_position(self, target_label, x: int, y: int, w: int, h: int, threshold: float = 0.8) -> bool:
        """
        检查目标标签是否存在于指定区域（支持部分重叠判断）
        :param y:
        :param x:
        :param w:
        :param h:
        :param target_label: 标签名
        :param threshold: IOU阈值
        """
        results = self._app_processor.latest_results
        if not results.exists_label(target_label):
            return False
        select_labels = results.filter_by_label(target_label)
        if not select_labels:
            return False
        # 当前检查区域
        x1, y1, x2, y2 = x, y, x + w, y + h
        for el in select_labels:
            ex1, ey1, ex2, ey2 = el.x, el.y, el.x + el.w, el.y + el.h
            # 计算交集
            inter_w = max(0, min(x2, ex2) - max(x1, ex1))
            inter_h = max(0, min(y2, ey2) - max(y1, ey1))
            inter_area = inter_w * inter_h
            # 计算并集
            union_area = (w * h) + (el.w * el.h) - inter_area
            iou = inter_area / union_area if union_area > 0 else 0
            if iou >= threshold:
                return True
        return False


    def check_image_change_at_position(self, x, y, w, h, original: Optional[np.ndarray] = None, timeout=10, threshold: float = 0.8) -> bool:
        """
        检查指定位置图像是否变化
        :param x:
        :param y:
        :param w:
        :param h:
        :param original: 原图
        :param timeout: 超时时间
        :param threshold: 图像变化阈值
        :return:
        """
        last_frame = original if original is not None and original.size > 0 else self._app_processor.latest_results.frame[y:h, x:w]
        last_frame = cv2.cvtColor(last_frame, cv2.COLOR_BGR2GRAY)
        wait_time = 0
        count = 0
        while True:
            if wait_time > timeout:
                return False
            current_frame = self._app_processor.latest_results.frame[y:h, x:w]
            current_frame = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
            if last_frame.shape == current_frame.shape:
                wait_time += 0.1
                sleep(0.1)
                continue
            score, diff = ssim(last_frame, current_frame, full=True)
            if score > threshold:
                count += 1
                if count >= 3:
                    return True
            else:
                wait_time += 1
                sleep(1)
        return False

    def check_image_change_at_yolobox(self, target_yolobox: Yolo_Box, timeout=10, threshold: float = 0.8) -> bool:
        """
        检查目标YoloBox位置的图像是否变化
        :param target_yolobox:
        :param timeout:
        :param threshold:
        :return:
        """
        return self.check_image_change_at_position(
            target_yolobox.x,
            target_yolobox.y,
            target_yolobox.w,
            target_yolobox.h,
            target_yolobox.frame,
            timeout,
            threshold
        )


    def click_button(self, text, timeout=10, match_config: MatchConfig = MatchConfig(use_fuzz=True, fuzz_threshold=80)):
        """
        点击指定文本按钮
        :param match_config:
        :param text: 按钮文本
        :param timeout: 超时时间
        :return:
        """
        logger.debug(f"waiting click button: {text}")
        self._app_processor.device.click_element(self.wait_button(text, timeout, match_config))

    def wait_button(self, text, timeout=10, match_config: MatchConfig = MatchConfig(use_fuzz=True, fuzz_threshold=80)):
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
                self._app_processor.device.click_element(self._app_processor.latest_results.filter_by_label(BaseUILabels.TAB_HOME).first())
                self.wait_loading()
                self.update_current_location()
                return
            elif go_home_btn := self._app_processor.latest_results.filter_by_label(BaseUILabels.GO_HOME_BTN):
                self._app_processor.device.click_element(go_home_btn.first())
                self.wait_loading()
                self.update_current_location()
                return
            elif modal_header := self._app_processor.latest_results.filter_by_label(BaseUILabels.MODAL_HEADER):
                modal_header = modal_header.first()
                self._app_processor.device.click(modal_header.cx, max(modal_header.y - 50, 0))
            sleep(1)
        raise RuntimeError("Going home failed")


    def back_next_page(self):
        """
        返回上一页
        :return:
        """
        logger.debug("Going back next page")
        if self.wait_for_label(BaseUILabels.BACK_BTN, 3):
            self._app_processor.device.click_element(self._app_processor.latest_results.filter_by_label(BaseUILabels.BACK_BTN).first())
        else:
            raise TimeoutError("Waiting for a back button timeout")

    def update_current_location(self, new_location: str = None):
        """
        更细游戏管理器中的当前位置
        :param new_location: 可选，直接按输入的位置
        :return:
        """
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

    def wait_frame_stable(self, threshold=0.98, stable_count=3, timeout=5):
        """
        等待画面稳定（SSIM）
        threshold: 画面相似度阈值
        stable_count: 连续多少帧满足才算稳定
        timeout: 超时时间（秒）
        """
        start = time()
        prev_frame = None
        stable_times = 0

        while True:
            curr_frame = self._app_processor.latest_frame
            if curr_frame is None:
                sleep(0.05)
                continue

            # 第一帧，无对比，跳过
            if prev_frame is None:
                prev_frame = curr_frame.copy()
                sleep(0.05)
                continue
            prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
            curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)

            score, _ = ssim(prev_gray, curr_gray, full=True)
            logger.info(f"SSIM: {score}")
            if score >= threshold:
                stable_times += 1
            else:
                stable_times = 0
            # 判断是否连续稳定
            if stable_times >= stable_count:
                return True

            if time() - start > timeout:
                return False

            prev_frame = curr_frame.copy()
            sleep(0.05)


