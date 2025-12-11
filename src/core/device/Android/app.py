import random
import time
from typing import Optional

import adbutils
import cv2
import numpy as np
import requests
import uiautomator2 as u2

from src.constants.device.adb import ADBConnectMode, ADBOperation
from src.core.services.config_service import ConfigService
from src.entity.BaseDevice import BaseDevice
from src.utils.adb_tools import start_DroidCast, ADBShell
from src.utils.logger import logger
from src.utils.performance_tools import timeit


class Android_App(BaseDevice):
    __config_service: ConfigService
    __adb_host: str
    __adb_port: int
    __adb_device: adbutils.AdbDevice
    __u2_device: Optional[u2.Device] = None
    __package_name: str
    __connect_mode: str
    __screen_capture_service: str
    __screen_touch_service: str
    __droidcast_service_status: bool = False
    __capture_service_shell: ADBShell = None

    def __init__(self) -> None:
        self.__config_service = ConfigService()
        self.__package_name = self.__config_service().base.game_package_name.value
        self.__connect_mode = self.__config_service().base.adb_connect_mode.value
        self.__adb_serial = self.__config_service().base.adb_serial.value
        self.__adb_host = self.__config_service().base.adb_host.value
        self.__adb_port = self.__config_service().base.adb_port.value
        self.__screen_capture_service = self.__config_service().base.android_screen_capture_service.value
        self.__screen_touch_service = self.__config_service().base.android_touch_service.value
        self.__connect_ADB()
        self.__init_capture_service()
        if (
            self.__screen_capture_service == ADBOperation.ScreenCaptureService.uiautomator2
            or self.__screen_touch_service ==  ADBOperation.TouchService.uiautomator2
        ):
            self.__connect_uiautomator2()

    def __del__(self) -> None:
        if self.__capture_service_shell is not None:
            self.__capture_service_shell.close()


    def __bool__(self) -> bool:
        return bool(self.__adb_device)

    def __connect_ADB(self) -> bool:
        if self.__connect_mode == ADBConnectMode.USB:
            if self.__adb_serial not in adbutils.adb.device_list():
                logger.error(f"Invalid ADB serial: {self.__adb_serial}")
                return False
            logger.debug(f"Tray connect ADB(serial: {self.__adb_serial})")
            try:
                self.__adb_device = adbutils.adb.device(serial=self.__adb_serial)
            except Exception as e:
                logger.error(f"ADB Connect Error: {e}")
                return False
            return True
        elif self.__connect_mode == ADBConnectMode.NETWORK:
            self._adb_host = self.__config_service().base.adb_host.value
            self._adb_port = self.__config_service().base.adb_port.value
            logger.debug(f"Tray connect ADB(host: {self._adb_host}, port: {self._adb_port})......")
            adbutils.adb.connect(f"{self.__adb_host}:{self.__adb_port}")
            try:
                self.__adb_device = adbutils.adb.device(f"{self.__adb_host}:{self.__adb_port}")
            except Exception as e:
                logger.error(f"ADB Connect Error: {e}")
                return False
            return True
        else:
            logger.error(f"Invalid connect mode: {self.__connect_mode}")
            return False

    def __connect_uiautomator2(self):
        logger.debug("Try connect to UIAutomator2...")
        try:
            self.__u2_device = u2.connect(self.__adb_device.serial)
        except Exception as e:
            logger.warning(f"uiautomator2 Initial Error：\n{e}")
            self.__u2_device = None

    def __init_capture_service(self):
        match self.__screen_capture_service:
            case ADBOperation.ScreenCaptureService.ADB:
                pass
            case ADBOperation.ScreenCaptureService.uiautomator2:
                pass
            case ADBOperation.ScreenCaptureService.DroidCast:
                self.__droidcast_service_status, self.__capture_service_shell = start_DroidCast(self.__adb_device)
            case _:
                logger.error(f"Not support capture service: {screen_capture_service}")

    def start_game(self):
        """启动游戏"""
        self.__adb_device.app_start(self.__package_name)
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
        if self.__u2_device is None:
            return self.__package_name in self.__adb_device.shell("dumpsys window windows | grep mCurrentFocus")
        return self.__package_name in self.__u2_device.info.get('currentPackageName')

    @timeit
    def is_app_running(self) -> bool:
        """判断游戏是否在运行"""
        if self.__u2_device is None:
            return self.__adb_device.shell(f"pidof {self.__package_name}").strip() != ""
        return self.__package_name in self.__u2_device.app_list_running()

    @timeit
    def get_window_size(self):
        if not self.__u2_device:
            return self.__adb_device.window_size()
        return self.__u2_device.window_size()

    def __get_touch_service(self):
        match self.__screen_touch_service:
            case ADBOperation.TouchService.uiautomator2:
                if self.__u2_device is not None:
                    return self.__u2_device
                return self.__adb_device
            case ADBOperation.TouchService.ADB:
                return self.__adb_device

    def _scroll(self, x, y, direction, scroll_delta):
        """
        通用滚动方法，模拟人类滑动
        :param x: 起始X坐标
        :param y: 起始Y坐标
        :param direction: ADBOperation.ScrollDirection.HORIZONTAL / VERTICAL
        :param scroll_delta: 正负代表方向，绝对值代表滚动次数
        """
        width, height = self.get_window_size()
        # 坐标安全限制
        x = max(50, min(width - 50, x))
        y = max(50, min(height - 50, y))

        scroll_distance = int(height * 0.05)  # 每次滚动的基础距离
        scroll_sign = 1 if scroll_delta > 0 else -1

        # 通过一定随机化来模拟人的滑动
        for _ in range(abs(scroll_delta)):
            # 随机化每次滑动的距离，模拟人手滑动的自然波动
            random_offset_x = random.randint(-10, 10)  # 随机偏移X轴
            random_offset_y = random.randint(-10, 10)  # 随机偏移Y轴

            # 控制滑动的加速度，模拟人类滑动的自然效果
            # 当滑动距离较远时，逐渐加速滑动
            scroll_factor = random.uniform(0.8, 1.2) if random.random() > 0.2 else random.uniform(1, 1.5)

            current_scroll_distance = int(scroll_distance * scroll_factor)

            # 人手滑动更不规则，采用随机化的轨迹
            if direction == ADBOperation.ScrollDirection.HORIZONTAL:
                start_x = x + random_offset_x
                end_x = x + scroll_sign * (current_scroll_distance) + random_offset_x
                self.__get_touch_service().swipe(start_x, y, end_x, y + random_offset_y, random.uniform(0.1, 0.2))
            elif direction == ADBOperation.ScrollDirection.VERTICAL:
                start_y = y + random_offset_y
                end_y = y + scroll_sign * (current_scroll_distance) + random_offset_y
                self.__get_touch_service().swipe(x + random_offset_x, start_y, x, end_y, random.uniform(0.1, 0.2))
            else:
                raise ValueError(f"Invalid direction: {direction}")

            # 增加随机的短暂停顿，模拟人类滑动中的自然停顿
            time.sleep(random.uniform(0.05, 0.1))

    def scrollY(self, x, y, scroll_delta):
        """纵向滚动（向上/向下滑动）"""
        self._scroll(x, y, ADBOperation.ScrollDirection.VERTICAL, scroll_delta)

    def scrollX(self, x, y, scroll_delta):
        self._scroll(x, y, ADBOperation.ScrollDirection.HORIZONTAL, scroll_delta)

    def click(self, x, y, el_label=""):
        """点击指定坐标"""
        self.__get_touch_service().click(x, y)

    def capture(self) -> np.ndarray:
        match self.__config_service().base.android_screen_capture_service.value:
            case ADBOperation.ScreenCaptureService.ADB:
                return cv2.cvtColor(np.asarray(self.__adb_device.screenshot()), cv2.COLOR_RGB2BGR)
            case ADBOperation.ScreenCaptureService.DroidCast:
                if not self.__droidcast_service_status:
                    return cv2.cvtColor(np.asarray(self.__adb_device.screenshot()), cv2.COLOR_RGB2BGR)
                response = requests.get("http://127.0.0.1:53516/screenshot")
                response.raise_for_status()
                image_array = np.frombuffer(response.content, dtype=np.uint8)
                return cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            case ADBOperation.ScreenCaptureService.uiautomator2:
                return self.__u2_device.screenshot(format='opencv')
            case _:
                raise RuntimeError(f"Can't capture screenshot")
