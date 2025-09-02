import threading
from threading import Thread
from time import sleep

import cv2
import numpy as np
from typing import Callable, List

import config
from src.constants.yolo.model_type import YoloModelType
from src.core.device.Android.app import Android_App
from src.core.device.Windows.app import Windows_App
from src.core.inference.ONNX import YoloModelFromONNX
from src.entity.WebSocketData import WebSocketData
from src.entity.Yolo import Yolo_Results
from src.utils.logger import logger



class YoloInferenceEngine:
    _engine: YoloModelFromONNX
    _device: Android_App | Windows_App
    _model_type: str
    _latest_frame: np.ndarray = None
    _latest_results: Yolo_Results | None = None
    _pause_capture_frame: bool = False
    _capture_thread: Thread
    _infer_callback_list: List[Callable]
    # Flags
    __flag_loop: bool = False  # 主循环
    __flag_pause: bool = False  # 暂停
    # Lock
    __action_lock: threading.Lock  # 动作锁
    __result_write_lock: threading.Lock  # 写入锁


    def __init__(self, device: Android_App | Windows_App):
        self._device = device
        self._infer_callback_list = []
        self.__action_lock = threading.Lock()
        self.__result_write_lock = threading.Lock()
        self.load_model()

    def load_model(self, model_type: str = YoloModelType.BASE_UI):
        """
        加载指定类型的Yolo模型
        :param model_type:
        :return:
        """
        if model_type not in YoloModelType.__dict__.keys() and model_type in config.model_config.keys():
            raise ValueError(f'Unknown model type: {model_type}')
        if self.__flag_loop:
            self.pause()
        with self.__action_lock:
            logger.debug(f"Loading YOLO model {model_type}...")
            self._engine = YoloModelFromONNX(config.model_config[model_type])
            self._model_type = model_type
        if self.__flag_loop:
            self.resume()

    def start(self):
        """
        开始推理进程
        :return:
        """
        with self.__action_lock:
            if self.__flag_loop:
                return False
            self.__flag_pause = False
            self.__flag_loop = True
            self._capture_thread = threading.Thread(target=self._inference_loop, daemon=True)
            self._capture_thread.start()
            logger.success("Started inference thread.")
        return True

    def stop(self):
        """
        结束推理进程
        :return:
        """
        with self.__action_lock:
            if not self.__flag_loop:
                return False
            self.__flag_pause = False
            self.__flag_loop = False
            self._capture_thread.join(timeout=3)
            logger.success("Stopped inference thread.")
        return True

    def pause(self):
        """
        暂停推理
        :return:
        """
        with self.__action_lock:
            if self.__flag_pause:
                return False
            self.__flag_pause = True
            logger.debug("Paused inference frame")
            return True

    def resume(self):
        """
        恢复推理
        :return:
        """
        with self.__action_lock:
            if not self.__flag_pause:
                return False
            self.__flag_pause = False
            logger.debug("Resumed inference frame")
            return True

    @property
    def is_pause(self):
        with self.__action_lock:
            return self.__flag_pause

    @property
    def running(self):
        with self.__action_lock:
            return self.__flag_loop

    @property
    def latest_frame(self):
        return self._latest_frame

    @property
    def latest_results(self):
        return self._latest_results

    @property
    def model_type(self):
        return self._model_type

    def register_infer_callback(self, func: Callable):
        with self.__action_lock:
            if func not in self._infer_callback_list:
                logger.debug(f"Register inference callback: {func.__name__}")
                self._infer_callback_list.append(func)
            else:
                logger.error(f"Inference callback already registered: {func}")


    def _exec_infer_callback(self):
        for callback in self._infer_callback_list:
            try:
                callback(self.latest_frame, self.latest_results)
            except Exception as e:
                logger.error(f"Inference callback failed: {e}")

    def _inference_loop(self):
        """
        截图并推理
        """
        while self.__flag_loop:
            if self.__flag_pause:
                sleep(0.1)
                continue
            frame = self._device.capture()
            if frame is None or frame.size <= 0:
                sleep(0.1)
                continue
            results = self._engine(frame)
            with self.__result_write_lock:
                self._latest_frame = frame
                self._latest_results = Yolo_Results(results, frame)
            self._exec_infer_callback()
        self.__flag_loop = False