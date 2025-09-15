import os
import webbrowser

import cv2

import config
from typing import Union, Callable, List
from fastapi import FastAPI
from time import sleep

from src.constants.device.device_type import DeviceType
from src.core.device.Android.app import Android_App
from src.core.inference.yolo_engine import YoloInferenceEngine
from src.core.services.task_service import TaskQueue
from src.core.services.clip_services import CLIPServiceManager
from src.core.Web.routers import register_routes
from src.core.Web.websocket import WebSocketManager
from src.core.device.Windows.app import Windows_App
from src.core.services.game_utils import GameUtils
from src.core.tasks.middlewares.middleware_register import register_middlewares
from src.core.services.config_service import ConfigService
from src.core.tasks.task_register import register_tasks
from src.entity.Game.Game_Info import GameStatusManager
from src.entity.WebSocketData import WebSocketData
from src.utils.debug_tools import DebugTools
from src.utils.logger import logger

# if TYPE_CHECKING:
#     from src.core.services.task_service import TaskQueue

class AppProcessor:
    data_path: str
    # 配置服务
    config_service: ConfigService
    # 操作设备
    device: Android_App | Windows_App
    # 任务队列
    task_queue: "TaskQueue"
    # Yolo推理引擎
    yolo_engine: YoloInferenceEngine
    # 图像debug工具
    debug_tools: DebugTools
    # 中间件注册列表
    _middleware_registry: List[Callable]
    # 游戏实用工具
    game_utils: GameUtils
    # 游戏状态管理器
    game_status_manager: GameStatusManager
    # 图像记忆管理器
    clip_manager: CLIPServiceManager
    # Websocket Session管理器
    ws_manager: WebSocketManager

    def __init__(self):
        self._init_environment()
        self._init_database()
        self.config_service = ConfigService()
        print(self.config_service())
        self.device = self._create_device_instance()
        self.yolo_engine = YoloInferenceEngine(self.device)
        self.debug_tools = DebugTools()
        self.yolo_engine.register_infer_callback(self._send_frame_to_clients)
        self._middleware_registry = []
        self.task_queue = TaskQueue(self)
        self.game_status_manager = GameStatusManager()
        self.game_utils = GameUtils(self)
        self.clip_manager = CLIPServiceManager()
        register_tasks(self)
        register_middlewares(self)
        self.ws_manager = WebSocketManager()
        register_routes(app, self, self.ws_manager)
        logger.success("Application Initialized")

    def _init_environment(self):
        self.data_path = os.path.join(os.getcwd(), "data")
        os.makedirs(self.data_path, exist_ok=True)

    @staticmethod
    def _init_database():
        from src.models.base import db
        from src.models import all_models
        if db.is_closed():
            db.connect()
        db.create_tables(all_models)
        db.close()
        logger.success("Database Initialized")

    @property
    def latest_frame(self):
        return self.yolo_engine.latest_frame

    @property
    def latest_results(self):
        return self.yolo_engine.latest_results

    def register_task(
            self,
            task_name: str,
            description: str,
            timeout: int | None = None,
            disabled_middleware: bool = False,
            manual_only: bool = False
    ):
        """
        注册任务
        :param task_name: 任务名（唯一）
        :param description: 任务介绍
        :param timeout: 超时时间
        :param disabled_middleware: 禁用中间件
        :param manual_only: 仅手动模式执行
        :return:
        """
        logger.debug(f"register task: {task_name}")
        def decorator(func: Callable):
            self.task_queue.reg_task(task_name, description, func, disabled_middleware, manual_only, timeout)
        return decorator

    def register_middleware(self):
        """
        注册中间件
        :return:
        """
        def decorator(func: Callable):
            logger.debug(f"register middleware: {func.__name__}")
            self._middleware_registry.append(func)
        return decorator

    def _create_device_instance(self) -> Union[Android_App, Windows_App]:
        """
        创建设备操作实例
        """
        mode = self.config_service().base.run_mode.value.lower()
        if mode == DeviceType.PHONE:
            logger.debug("Initializing Android mode")
            return Android_App(
                self.config_service().base.adb_connect_mode.value,
                self.config_service().base.game_package_name.value,
                self.config_service().base.adb_host.value,
                self.config_service().base.adb_port.value,
                self.config_service().base.adb_serial.value,
            )
        if mode == DeviceType.PC:
            logger.debug("Initializing Windows mode")
            return Windows_App(
                self.config_service().base.game_window_name.value
            )
        raise ValueError(f"Invalid device type: {mode}")

    def _send_frame_to_clients(self, latest_frame, latest_results):
        """将最新的图像的二进制数据发送给 WebSocket 客户端。"""
        if latest_frame is None:
            return
        # 获取图像尺寸
        height, width = latest_frame.shape[:2]
        if not latest_results:
            _, encoded_frame = cv2.imencode('.jpg', latest_frame)
            frame_bytes = encoded_frame.tobytes()
            self.ws_manager.broadcast_sync(WebSocketData(None, f"{width},{height}".encode('utf-8') + b"," + frame_bytes))
        annotated_frame = latest_results.results.plot()
        annotated_frame = self.debug_tools.draw_boxes(annotated_frame)
        _, encoded_frame = cv2.imencode('.jpg', annotated_frame)
        frame_bytes = encoded_frame.tobytes()
        self.ws_manager.broadcast_sync(WebSocketData(None, f"{width},{height}".encode('utf-8') + b"," + frame_bytes))

    def exec_middleware(self):
        """
        执行中间件
        :return:
        """
        flag: bool = True
        for func in self._middleware_registry:
            if func(self) is False:
                logger.debug(f"{func.__name__} return false")
                flag = False
        return flag

    def exec_task(self, task_name: str = None):
        if isinstance(self.device, Windows_App):
            self.device.bring_to_front()
            sleep(0.5)
        return self.task_queue.exec_task(task_name)


app = FastAPI()
processor = AppProcessor()


@app.on_event("shutdown")
def shutdown_event():
    processor.yolo_engine.stop()

@app.on_event("startup")
def start_event():
    processor.yolo_engine.start()
    # processor.yolo_engine.pause()
    url = f"http://{config.web_server_host}:{config.web_server_port}"
    if config.auto_open_web_browser:
        webbrowser.open(url)
    logger.success(f"Server started at {url}")