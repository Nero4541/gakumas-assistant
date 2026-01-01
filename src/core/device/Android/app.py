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
from src.utils.debug_tools import DebugTools
from src.utils.logger import logger
from src.utils.performance_tools import timeit


debugger = DebugTools()

class Android_App(BaseDevice):
    __config_service: ConfigService
    __adb_host: str
    __adb_port: int
    __adb_device: adbutils.AdbDevice = None
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
        if not self.__connect_ADB():
            return
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
            if self.__adb_serial not in [dev.serial for dev in adbutils.adb.device_list()]:
                logger.error(f"Invalid ADB serial: {self.__adb_serial}")
                return False
            logger.debug(f"Try connect ADB(serial: {self.__adb_serial})")
            try:
                self.__adb_device = adbutils.adb.device(serial=self.__adb_serial)
            except Exception as e:
                logger.error(f"ADB Connect Error: {e}")
                return False
            return True
        elif self.__connect_mode == ADBConnectMode.NETWORK:
            self._adb_host = self.__config_service().base.adb_host.value
            self._adb_port = self.__config_service().base.adb_port.value
            logger.debug(f"Try connect ADB(host: {self._adb_host}, port: {self._adb_port})......")
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
                self.__screen_capture_service = ADBOperation.ScreenCaptureService.ADB
                self.__config_service().base.android_screen_capture_service.value = ADBOperation.ScreenCaptureService.ADB
                self.__config_service.save_config()
                logger.warning(f"Not support capture service: '{self.__screen_capture_service}', reverted to ADB")

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
            case _:
                self.__screen_touch_service = ADBOperation.TouchService.ADB
                self.__config_service().base.android_touch_service.value = ADBOperation.TouchService.ADB
                self.__config_service.save_config()
                logger.warning(f"Not support touch service: '{self.__screen_touch_service}', reverted to ADB")
                return self.__adb_device

    def swipe(self, start_x, start_y, end_x, end_y, duration=0.8):
        """
        基础滑动方法：执行带安全检查和随机偏移的单次滑动
        :param start_x: 起始X
        :param start_y: 起始Y
        :param end_x: 结束X
        :param end_y: 结束Y
        :param duration: 滑动总时长，默认0.8秒
        """
        width, height = self.get_window_size()
        def clamp(val, max_val):
            return max(50, min(max_val - 50, val))
        safe_start_x = clamp(start_x, width)
        safe_start_y = clamp(start_y, height)
        safe_end_x = clamp(end_x, width)
        safe_end_y = clamp(end_y, height)
        debugger.add_line(
            safe_start_x,
            safe_start_y,
            safe_end_x,
            safe_end_y,
            color=(0, 255, 0),   # 绿色滑动轨迹
            thickness=3,
            duration=duration+1
        )
        debugger.add_point(
            safe_start_x,
            safe_start_y,
            color=(255, 255, 0), # 起点黄
            radius=6,
            duration=duration+1
        )
        debugger.add_point(
            safe_end_x,
            safe_end_y,
            color=(255, 0, 0),   # 终点红
            radius=6,
            duration=duration+1
        )
        # 模拟人类滑动的微小随机偏移 (轨迹随机化)
        offset_x = random.randint(-10, 10)
        offset_y = random.randint(-10, 10)
        # 将 duration 稍微随机化，避免死板的固定时长
        actual_duration = duration * random.uniform(0.9, 1.1)
        self.__get_touch_service().swipe(
            safe_start_x + offset_x,
            safe_start_y + offset_y,
            safe_end_x,
            safe_end_y,
            actual_duration
        )
        # 增加随机短暂停顿 (模拟人类自然停顿)
        time.sleep(random.uniform(0.05, 0.1))

    def _scroll(self, x, y, direction, scroll_delta):
        """
        通用滚动方法，调用提取出的 swipe
        """
        width, height = self.get_window_size()
        scroll_distance = int(height * 0.05)
        scroll_sign = 1 if scroll_delta > 0 else -1

        for _ in range(abs(scroll_delta)):
            # 计算滑动因子和当前距离
            scroll_factor = random.uniform(0.8, 1.2) if random.random() > 0.2 else random.uniform(1, 1.5)
            current_dist = int(scroll_distance * scroll_factor)

            if direction == ADBOperation.ScrollDirection.HORIZONTAL:
                end_x = x + (scroll_sign * current_dist)
                DebugTools().add_line(
                    x, y, x, end_x,
                    color=(100, 200, 255),
                    thickness=2,
                    duration=1.0
                )
                self.swipe(x, y, end_x, y, duration=random.uniform(0.1, 0.2))

            elif direction == ADBOperation.ScrollDirection.VERTICAL:
                end_y = y + (scroll_sign * current_dist)
                DebugTools().add_line(
                    x, y, x, end_y,
                    color=(100, 200, 255),
                    thickness=2,
                    duration=1.0
                )
                self.swipe(x, y, x, end_y, duration=random.uniform(0.1, 0.2))
            else:
                raise ValueError(f"Invalid direction: {direction}")

    def scrollY(self, x, y, scroll_delta):
        """纵向滚动（向上/向下滑动）"""
        self._scroll(x, y, ADBOperation.ScrollDirection.VERTICAL, scroll_delta)

    def scrollX(self, x, y, scroll_delta):
        self._scroll(x, y, ADBOperation.ScrollDirection.HORIZONTAL, scroll_delta)

    def click(self, x, y, el_label=""):
        """点击指定坐标"""
        debugger.add_crosshair(
            x, y,
            size=25,
            color=(255, 0, 0),
            thickness=1
        )
        self.__get_touch_service().click(x, y)

    def capture(self) -> Optional[np.ndarray]:
        if not self.__bool__():
            return None
        match self.__config_service().base.android_screen_capture_service.value:
            case ADBOperation.ScreenCaptureService.ADB:
                return cv2.cvtColor(np.asarray(self.__adb_device.screenshot()), cv2.COLOR_RGB2BGR)
            case ADBOperation.ScreenCaptureService.DroidCast:
                if not self.__droidcast_service_status:
                    return cv2.cvtColor(np.asarray(self.__adb_device.screenshot()), cv2.COLOR_RGB2BGR)
                response = requests.get("http://127.0.0.1:53516/screenshot")
                if response.status_code != 200:
                    self.__init_capture_service()
                    return cv2.cvtColor(np.asarray(self.__adb_device.screenshot()), cv2.COLOR_RGB2BGR)
                image_array = np.frombuffer(response.content, dtype=np.uint8)
                return cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            case ADBOperation.ScreenCaptureService.uiautomator2:
                return self.__u2_device.screenshot(format='opencv')
            case _:
                logger.warning(f"Undefined screenshot service {self.__config_service().base.android_screen_capture_service.value}, reverted to ADB")
                return cv2.cvtColor(np.asarray(self.__adb_device.screenshot()), cv2.COLOR_RGB2BGR)
