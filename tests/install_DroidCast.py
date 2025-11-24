import os
import re
import threading
from time import sleep
from typing import Callable

import adbutils
import cv2
import numpy as np
import requests
from adbutils import AdbDevice

from src.constants.device.adb import ADBOperation
from src.utils.adb_tools import ADBShell, start_DroidCast
from src.utils.logger import logger

adb_host = "127.0.0.1"
adb_port = 16384
# logger.debug(f"Tray connect ADB(host: {self._adb_host}, port: {self._adb_port})......")
adbutils.adb.connect(f"{adb_host}:{adb_port}")
adb_device = adbutils.adb.device(f"{adb_host}:{adb_port}")
adb_shell = ADBShell(adb_device)
# adb_shell.open_message(print)

def _install_DroidCast():
    adb_device.sync.push(os.path.join(os.getcwd(), "..", ADBOperation.ScreenCaptureService.Bin.DroidCast), "/data/local/tmp")
    adb_device.install_remote(f"/data/local/tmp/{os.path.basename(ADBOperation.ScreenCaptureService.Bin.DroidCast)}")
    adb_shell.send_command(fr"export CLASSPATH=/data/local/tmp/{os.path.basename(ADBOperation.ScreenCaptureService.Bin.DroidCast)}")
    adb_shell.send_command(f"exec app_process /system/bin com.rayworks.droidcast.Main '$@'")
    adb_device.forward("tcp:53516", "tcp:53516")
    logger.debug(f"start to http://localhost:53516/screenshot")


_install_DroidCast()
headers = {
    'Accept': 'image/jpeg',  # 根据服务器的返回类型调整
}
cv2.namedWindow("image", cv2.WINDOW_NORMAL)

while True:
    response = requests.get("http://127.0.0.1:53516/screenshot", headers=headers)
    # response.raise_for_status()
    if response.status_code != 200:
        print(f"get screenshot failed(code: {response.status_code} content: {response.content})")
        continue
    if not response.content:
        raise RuntimeError(f"Get screenshot failed")
    image_array = np.frombuffer(response.content, dtype=np.uint8)
    cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    cv2.imshow("image", cv2.imdecode(image_array, cv2.IMREAD_COLOR))
    cv2.waitKey(1)
sleep(30)
# del adb_shell
# sleep(10)
