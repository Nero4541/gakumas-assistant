import time
from typing import Optional

import adbutils
import uiautomator2 as u2
import numpy as np
import cv2

from src.constants.device.adb import ADBConnectMode, ADBOperation
from src.core.services.config_service import ConfigService
from src.entity.BaseDevice import BaseDevice
from src.utils.logger import logger
from src.utils.performance_tools import timeit


class Android_App(BaseDevice):
    _adb_host: str
    _adb_port: int
    _adb_device: adbutils.AdbDevice
    _u2_device: Optional[u2.Device]
    _package_name: str
    _connect_mode: str

    def __init__(self, connect_mode: str, package_name: str, adb_host: str, adb_port: int, serial: str) -> None:
        """
        :param connect_mode: 连接模式
        :param package_name: App包名
        :param adb_host: ADB 地址
        :param adb_port: ADB tcpip端口
        :param serial: ADB USB端口
        """
        self._package_name = package_name
        self._connect_mode = connect_mode
        if connect_mode == ADBConnectMode.USB:
            if serial not in adbutils.adb.device_list():
                raise ValueError(f"Invalid ADB serial: {serial}")
            self._adb_device = adbutils.adb.device(serial=serial)
        elif connect_mode == ADBConnectMode.NETWORK:
            self._adb_host = adb_host
            self._adb_port = adb_port
            adbutils.adb.connect(f"{adb_host}:{adb_port}")
            self._adb_device = adbutils.adb.device(f"{adb_host}:{adb_port}")
        else:
            raise ValueError(f"Invalid connect mode: {connect_mode}")
        try:
            self._u2_device = u2.connect(self._adb_device.serial)
        except Exception as e:
            logger.warning(f"uiautomator2 Initial Error：\n{e}")
            self._u2_device = None

    # def connect(self) -> bool:
    #     config_service = ConfigService()
    #     match config_service().base.android_screen_capture_service.value:
    #         case ADBOperation.ScreenCaptureService.ADB
    #
    # def __connect_ADB(self) -> bool:
    #     if connect_mode == ADBConnectMode.USB:
    #         if serial not in adbutils.adb.device_list():
    #             raise ValueError(f"Invalid ADB serial: {serial}")
    #         self._adb_device = adbutils.adb.device(serial=serial)
    #         elif connect_mode == ADBConnectMode.NETWORK:
    #         self._adb_host = adb_host
    #         self._adb_port = adb_port
    #         adbutils.adb.connect(f"{adb_host}:{adb_port}")
    #         self._adb_device = adbutils.adb.device(f"{adb_host}:{adb_port}")


    def start_game(self):
        """启动游戏"""
        self._adb_device.app_start(self._package_name)
        TIMEOUT = 30
        COUNT = 0
        while True:
            if COUNT > TIMEOUT:
                raise TimeoutError("Waiting start game timeout")
            if self.is_app_focused:
                break
            else:
                time.sleep(1)
                COUNT += 1

    @timeit
    def is_app_focused(self) -> bool:
        """判断游戏是否在前台"""
        return self._package_name in self._u2_device.info.get('currentPackageName')

    @timeit
    def get_window_size(self):
        if not self._u2_device:
            return self._adb_device.window_size()
        return self._u2_device.window_size()

    def _scroll(self, x, y, direction, scroll_delta):
        """
        通用滚动方法
        :param x: 起始X坐标
        :param y: 起始Y坐标
        :param direction: ADBOperation.ScrollDirection.HORIZONTAL / VERTICAL
        :param scroll_delta: 正负代表方向，绝对值代表滚动次数
        """
        width, height = self.get_window_size()
        # 坐标安全限制
        x = max(50, min(width - 50, x))
        y = max(50, min(height - 50, y))

        swipe = (self._u2_device or self._adb_device).swipe

        scroll_distance = int(height * 0.05)  # 每次滚动距离
        scroll_sign = 1 if scroll_delta > 0 else -1

        for _ in range(abs(scroll_delta)):
            if direction == ADBOperation.ScrollDirection.HORIZONTAL:
                swipe(x, y, x + scroll_sign * scroll_distance, y, 0.1)
            elif direction == ADBOperation.ScrollDirection.VERTICAL:
                swipe(x, y, x, y + scroll_sign * scroll_distance, 0.1)
            else:
                raise ValueError(f"Invalid direction: {direction}")



    def scrollY(self, x, y, scroll_delta):
        """纵向滚动（向上/向下滑动）"""
        # scroll_delta > 0 表示向上滑动（手指向下划）
        # if not self._u2_device:
        #     self._adb_device.swipe(x, y, x, y - scroll_delta, 0.3)
        #     return
        # self._u2_device.swipe(x, y, x, y - scroll_delta, 0.3)
        self._scroll(x, y, ADBOperation.ScrollDirection.VERTICAL, scroll_delta)

    def scrollX(self, x, y, scroll_delta):
        # if not self._u2_device:
        #     self._adb_device.swipe(x, y, x - scroll_delta * 50, y, 0.3)
        #     return
        # self._u2_device.swipe(x, y, x - scroll_delta * 50, y, 0.3)
        self._scroll(x, y, ADBOperation.ScrollDirection.HORIZONTAL, scroll_delta)

    def click(self, x, y, el_label=""):
        """点击指定坐标"""
        if not self._u2_device:
            self._adb_device.click(x, y)
            return
        self._u2_device.click(x, y)

    def capture(self) -> np.ndarray:
        return cv2.cvtColor(np.asarray(self._adb_device.screenshot()),cv2.COLOR_RGB2BGR)

        # if not self._u2_device:
        #     return cv2.cvtColor(np.asarray(self._adb_device.screenshot()),cv2.COLOR_RGB2BGR)
        # return self._u2_device.screenshot(format='opencv')
