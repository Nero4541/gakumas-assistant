import numpy as np

from src.entity.BaseDevice import BaseDevice
from src.entity.Yolo import Yolo_Box, Yolo_Results


class Android_App(BaseDevice):
    _adb_host: str
    _adb_port: int
    _package_name: str
    def __init__(self, adb_host: str, adb_port: int, package_name: str):
        self._adb_host = adb_host
        self._adb_port = adb_port
        self._package_name = package_name

    def scrollY(self, x, y, scroll_delta):
        pass

    def click_element(self, element: Yolo_Box | Yolo_Results):
        pass

    def click(self, x, y, el_label=""):
        pass

    def capture(self) -> np.ndarray:
        pass