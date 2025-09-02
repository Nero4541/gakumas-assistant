import adbutils
import numpy as np
import cv2

from src.constants.device.adb_connect_mode import ADBConnectMode
from src.entity.BaseDevice import BaseDevice

class Android_App(BaseDevice):
    _adb_host: str
    _adb_port: int
    _package_name: str

    def __init__(self, connect_mode: str, package_name: str, adb_host: str, adb_port: int, serial: str) -> None:
        """
        :param connect_mode: 连接模式
        :param package_name: App包名
        :param adb_host: ADB 地址
        :param adb_port: ADB tcpip端口
        :param serial: ADB USB端口
        """
        if connect_mode not in ADBConnectMode.__dict__.keys():
            raise ValueError(f"Invalid connect mode: {connect_mode}")
        self._package_name = package_name
        if connect_mode == ADBConnectMode.USB:
            if serial not in adbutils.adb.device_list():
                raise ValueError(f"Invalid ADB serial: {serial}")
            self._device = adbutils.adb.device(serial=serial)
        elif connect_mode == ADBConnectMode.NETWORK:
            self._adb_host = adb_host
            self._adb_port = adb_port
            adbutils.adb.connect(f"{adb_host}:{adb_port}")
            self._device = adbutils.adb.device(f"{adb_host}:{adb_port}")


    def startGame(self):
        """启动游戏"""
        self._device.app_start(self._package_name)

    def is_app_focused(self) -> bool:
        """判断游戏是否在前台"""
        info = self._device.app_current()
        return info.package == self._package_name

    def scrollY(self, x, y, scroll_delta):
        """纵向滚动（向上/向下滑动）"""
        # scroll_delta > 0 表示向上滑动（手指向下划）
        self._device.swipe(x, y, x, y - scroll_delta, 0.3)

    def click(self, x, y, el_label=""):
        """点击指定坐标"""
        print(f"Click {el_label} at ({x}, {y})")
        self._device.click(x, y)

    def capture(self) -> np.ndarray:
        png_bytes = self._device.screencap()
        img = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_COLOR)
        return img
