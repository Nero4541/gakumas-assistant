import ctypes
import os
import subprocess
import sys
from time import sleep
from typing import Tuple

import cv2
import numpy as np
import pyautogui
import pythoncom
import win32api
import win32com.client
import win32con
import win32gui

from src.core.services.config_service import ConfigService
from src.entity.BaseDevice import BaseDevice
from src.utils.logger import logger
from src.utils.system_tools import is_compiled


class Windows_App(BaseDevice):
    __window_name: str
    __cached_hwnd: int = None
    __config_service: ConfigService

    def __init__(self):
        if not self._is_admin():
            logger.warning("当前不是管理员权限，正在尝试使用管理员权限重启...")
            if is_compiled():
                args = " ".join(sys.argv[1:])
            else:
                args = " ".join(sys.argv)
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, args, None, 1)
            sys.exit()
        ctypes.windll.user32.SetProcessDPIAware()

        self.__config_service = ConfigService()
        self.__window_name = self.__config_service().base.game_window_name.value

    def __bool__(self) -> bool:
        return bool(win32gui.FindWindow(None, self.__window_name))

    @staticmethod
    def _is_admin():
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    def __find_window(self):
        """
        获取窗口实例
        """
        if self.__cached_hwnd and win32gui.IsWindow(self.__cached_hwnd):
            return self.__cached_hwnd
        hwnd = win32gui.FindWindow(None, self.__window_name)
        if not hwnd:
            raise Exception(f'Window "{self.__window_name}" not found')
        self.__cached_hwnd = hwnd
        return hwnd

    def __get_window_region(self):
        """
        获取窗口位置
        :return:
        """
        hwnd = self.__find_window()
        client_rect = win32gui.GetClientRect(hwnd)
        client_left, client_top = win32gui.ClientToScreen(hwnd, (0, 0))
        client_width = client_rect[2]  # 客户区宽度
        client_height = client_rect[3]  # 客户区高度
        return client_left, client_top, client_width, client_height

    def start_game(self):
        """
        启动游戏
        :return:
        """
        dmm_play_config = self.__config_service().dmm_player
        game_path = dmm_play_config.game_exe_path.value
        try:
            subprocess.Popen(
                [
                    game_path,
                    f"/viewer_id={dmm_play_config.viewer_id.value}",
                    f"/open_id={dmm_play_config.open_id.value}",
                    f"/pf_access_token={dmm_play_config.pf_token.value}"
                ],
                cwd=os.path.dirname(game_path),
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        except FileNotFoundError:
            logger.warning(f"Game launch failed: target file not found: {game_path}")
            return False
        except PermissionError as e:
            logger.warning(f"Game launch failed: permission error: {e}")
            return False
        except Exception as e:
            logger.warning(f"Game launch failed: {e}")
            return False
        return True

    @logger.catch
    def bring_to_front(self):
        """
        将窗口切换到前台
        """
        pythoncom.CoInitialize()  # 初始化COM
        try:
            hwnd = self.__find_window()
            win32gui.BringWindowToTop(hwnd)

            shell = win32com.client.Dispatch("WScript.Shell")
            shell.SendKeys('%')

            win32gui.SetForegroundWindow(hwnd)
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        finally:
            pythoncom.CoUninitialize()  # 用完后释放

    @logger.catch
    def is_app_focused(self):
        """
        判断游戏窗口是否处于焦点（前台）
        """
        try:
            hwnd = self.__find_window()
            foreground_hwnd = win32gui.GetForegroundWindow()
            if hwnd == foreground_hwnd:
                return True
            active_parent = win32gui.GetParent(foreground_hwnd)
            if active_parent and active_parent == hwnd:
                return True
            active_title = win32gui.GetWindowText(foreground_hwnd)
            return active_title == self.__window_name
        except Exception as e:
            logger.error(f"检测窗口焦点失败: {e}")
            return False

    def is_app_running(self) -> bool:
        """
        判断游戏进程是否正在运行
        """
        hwnd = win32gui.FindWindow(None, self.__window_name)
        return hwnd != 0

    @logger.catch
    def capture(self):
        """
        截取窗口位置
        :return:
        """
        client_left, client_top, client_width, client_height = self.__get_window_region()
        # 截取客户区域
        screenshot = pyautogui.screenshot(
            region=(client_left, client_top, client_width, client_height)
        )

        # 转换为 OpenCV 格式
        img = np.array(screenshot)
        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    def _xy_abs_conversion(self, x, y) -> Tuple[int, int]:
        left, top, width, height = self.__get_window_region()
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError(f"坐标超出有效范围: ({x}, {y}) 窗口尺寸: {width}x{height}")
        abs_x = left + x
        abs_y = top + y
        return abs_x, abs_y

    def click(self, x, y, el_label = ""):
        """
        点击窗口内容
        :param el_label:
        :param x:
        :param y:
        :return:
        """
        abs_x, abs_y = self._xy_abs_conversion(x, y)
        pyautogui.click(abs_x, abs_y, button='left')
        logger.debug(f"click {el_label}: {abs_x, abs_y}" if el_label else f"click: {abs_x, abs_y}")
        return True

    def scrollY(self, x, y, scroll_delta):
        if scroll_delta == 0:
            logger.warning("scroll delta is 0, skipping scroll")
            return
        abs_x, abs_y = self._xy_abs_conversion(x, y)
        pyautogui.moveTo(abs_x, abs_y)
        for _ in range(abs(scroll_delta)):
            win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0,120 if scroll_delta > 0 else -120)
            sleep(0.1)
        logger.debug(f"scroll delta: {scroll_delta} (x:{abs_x} y:{abs_y})")

    def scrollX(self, x, y, scroll_delta):
        pass