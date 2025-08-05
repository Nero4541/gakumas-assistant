import os
import sys
import threading
import webbrowser

import cv2
import numpy as np

import config
from typing import Union, Callable, List
from fastapi import FastAPI
from time import sleep

from src.core.ONNX import YoloModelFromONNX
from src.core.Android.app import Android_App
from src.core.CLIP_services.services import CLIPServiceManager
from src.core.Web.routers import register_routes
from src.core.Web.websocket import WebSocketManager
from src.core.Windows.app import Windows_App
from src.core.game_utils import GameUtils
from src.core.middlewares.middleware_register import register_middlewares
from src.core.tasks.task_register import register_tasks
from src.entity.Game.Game_Info import GameStatusManager
from src.entity.WebSocket_Data import WebSocket_Data
from src.core.task import TaskQueue
from src.entity.Yolo import YoloModelType, Yolo_Results
from src.utils.debug_tools import DebugTools
from src.utils.logger import logger


class AppProcessor:
    data_path: str
    # Yolo模型
    model: YoloModelFromONNX
    # 操作设备
    app: Android_App | Windows_App
    # 当前Yolo模型
    current_model_type: str
    # 画面Debug工具
    debug_tools: DebugTools
    # 最新帧
    latest_frame: np.array = None
    # 最新推理结果
    latest_results: Yolo_Results | None = None
    # 任务队列
    task_queue: TaskQueue
    # 捕获帧状态
    running: bool = False
    # 捕获帧线程
    capture_thread: threading.Thread = None
    # 暂停捕获帧标志
    _pause_capture_frame: bool = False
    # 中间件注册列表
    _middleware_registry: List[Callable]
    # 游戏实用工具
    game_utils: GameUtils
    # 游戏状态管理器
    game_status_manager: GameStatusManager
    # 图像记忆管理器
    clip_manager: CLIPServiceManager

    def __init__(self):
        self._init_environment()
        self._init_database()
        self.app = self._create_app_instance()
        self.load_model()
        self._middleware_registry = []
        self.task_queue = TaskQueue(self)
        self.game_status_manager = GameStatusManager()
        self.game_utils = GameUtils(self)
        self.clip_manager = CLIPServiceManager()
        self.debug_tools = DebugTools()
        register_tasks(self)
        register_middlewares(self)
        self.start()
        logger.success("Application Initialized")

    def _init_environment(self):
        logger.add(sys.stdout, level="DEBUG" if config.debug else "INFO")
        self.data_path = os.path.join(os.getcwd(), "data")
        os.makedirs(self.data_path, exist_ok=True)
        os.makedirs(os.path.join(self.data_path, "CLIP/data"), exist_ok=True)
        os.makedirs(os.path.join(self.data_path, "CLIP/images"), exist_ok=True)

    @staticmethod
    def _init_database():
        from src.models.base import db
        from src.models import all_models
        db.connect()
        db.create_tables(all_models)
        db.close()
        logger.success("Database Initialized")

    def load_model(self, model_type: str = YoloModelType.BASE_UI):
        """
        加载指定类型的Yolo模型
        :param model_type:
        :return:
        """
        def _init(model_type: str):
            logger.debug(f"Loading YOLO model {model_type}...")
            model_config = config.model_config.get(model_type)
            model = YoloModelFromONNX(model_config.get("model_path"))
            return model

        if model_type in [YoloModelType.BASE_UI, YoloModelType.PRODUCER]:
            self.pause_capture_frame()
            self.model = _init(model_type)
            self.current_model_type = model_type
            self.resume_capture_frame()
        else:
            raise ValueError(f'Unknown model type: {model_type}')

    def register_task(self, task_name: str, description: str, timeout: int | None = None):
        """实例方法：注册任务"""
        logger.debug(f"register task: {task_name}")
        def decorator(func: Callable):
            self.task_queue.reg_task(task_name, description, func, timeout)
        return decorator

    def register_middleware(self):
        """实例方法：注册中间件"""
        def decorator(func: Callable):
            logger.debug(f"register middleware: {func.__name__}")
            self._middleware_registry.append(func)
        return decorator

    def pause_capture_frame(self):
        if self.running and not self._pause_capture_frame:
            logger.debug("Pause capture frame......")
            self._pause_capture_frame = True
            self.capture_thread.join()
            logger.debug("Paused capture frame")

    def resume_capture_frame(self):
        if self.running and self._pause_capture_frame:
            self._pause_capture_frame = False
            self.capture_thread = threading.Thread(target=self._capture_and_infer, daemon=True)
            self.capture_thread.start()
            logger.debug("Resumed capture frame")

    @staticmethod
    def _create_app_instance() -> Union[Android_App, Windows_App]:
        """
        创建App操作实例
        """
        mode = config.mode.lower()
        if mode == 'phone':
            logger.debug("Initializing Android mode")
            return Android_App()
        if mode == 'pc':
            logger.debug("Initializing Windows mode")
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
            return Windows_App(config.window_name)
        raise ValueError(f"Invalid mode: {config.mode}")

    def _capture_and_infer(self):
        """
        截图并推理
        """
        while self.running and not self._pause_capture_frame:
            frame = self.app.capture()
            if frame is None or frame.size <= 0:
                sleep(0.3)
                continue
            self.latest_frame = frame
            results = self.model(frame)
            self.latest_results = Yolo_Results(results, frame)
            self._send_frame_to_clients()

    @logger.catch
    def _send_frame_to_clients(self):
        """将最新的图像的二进制数据发送给 WebSocket 客户端。"""
        if self.latest_frame is None:
            return
        # 获取图像尺寸
        height, width = self.latest_frame.shape[:2]
        if not self.latest_results.results:
            _, encoded_frame = cv2.imencode('.jpg', self.latest_frame)
            frame_bytes = encoded_frame.tobytes()
            ws_manager.broadcast_sync(WebSocket_Data(None, f"{width},{height}".encode('utf-8') + b"," + frame_bytes))
        annotated_frame = self.latest_results.results.plot()
        annotated_frame = self.debug_tools.draw_boxes(annotated_frame)
        _, encoded_frame = cv2.imencode('.jpg', annotated_frame)
        frame_bytes = encoded_frame.tobytes()
        ws_manager.broadcast_sync(WebSocket_Data(None, f"{width},{height}".encode('utf-8') + b"," + frame_bytes))

    def exec_middleware(self):
        """注册处理中间件"""
        flag: bool = True
        for func in self._middleware_registry:
            if func(self) is False:
                flag = False
        return flag

    def start(self):
        if not self.running or self._pause_capture_frame:
            self.running = True
            self.capture_thread = threading.Thread(target=self._capture_and_infer, daemon=True)
            self.capture_thread.start()
            logger.success("Started inference thread.")

    def stop(self):
        if self.running:
            self.running = False
            self.capture_thread.join(timeout=3)
            logger.success("Stopped inference thread.")

    def exec_task(self, task_name: str = None):
        if isinstance(self.app, Windows_App):
            self.app.bring_to_front()
            sleep(0.5)
        return self.task_queue.exec_task(task_name)


app = FastAPI()
processor = AppProcessor()
ws_manager = WebSocketManager()

register_routes(app, processor, ws_manager)

@app.on_event("shutdown")
def shutdown_event():
    processor.stop()

@app.on_event("startup")
def start_event():
    processor.start()
    if config.auto_open_web_browser:
        webbrowser.open(f"http://{config.web_server_host}:{config.web_server_port}")