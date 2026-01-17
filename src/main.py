import os
import shutil
import webbrowser

import cv2

import config
from typing import Union, Callable, List
from fastapi import FastAPI
from time import sleep

from src.constants.path.data_path import DataPath
from src.constants.path.debug_path import DebugPath
from src.constants.device.device_type import DeviceType
from src.constants.task_status import TaskStatus
from src.core.device.Android.app import Android_App
from src.core.inference.yolo_engine import YoloInferenceEngine
from src.core.services.task_service import TaskService
from src.core.services.clip_services import CLIPServiceManager
from src.core.web.routers import register_routes
from src.core.web.websocket import WebSocketManager
from src.core.device.Windows.app import Windows_App
from src.core.services.game_utils import GameUtils
from src.core.tasks.middlewares.middleware_register import register_middlewares
from src.core.services.config_service import ConfigService
from src.core.tasks.task_register import register_tasks
from src.entity.BaseDevice import BaseDevice
from src.entity.Game.Game_Info import GameStatusManager
from src.entity.WebSocketData import WebSocketData
from src.utils.debug_tools import DebugTools
from src.utils.dmm_tools import extract_gakumas_launch_parameters
from src.utils.logger import logger

class AppProcessor:
    data_path: str
    # 配置服务
    config_service: ConfigService
    # 操作设备
    device: BaseDevice
    # 任务队列
    task_queue: TaskService
    # Yolo推理引擎
    yolo_engine: YoloInferenceEngine
    # 图像debug工具
    debug_tools: DebugTools
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
        logger.debug(self.config_service())
        self.device = self.create_device_instance()
        self.yolo_engine = YoloInferenceEngine(self.device)
        self.clip_manager = CLIPServiceManager()
        self.debug_tools = DebugTools()
        self.yolo_engine.register_infer_callback(self._send_frame_to_clients)
        self.task_queue = TaskService(self)
        self.game_status_manager = GameStatusManager()
        self.game_utils = GameUtils(self)
        self.ws_manager = WebSocketManager()
        register_tasks(self)
        register_middlewares(self)
        self._register_config_listening()
        self._load_game_database()
        logger.success("Application Initialized")

    def _init_environment(self):
        """
        初始化环境
        """
        self.data_path = os.path.join(os.getcwd(), "data")
        os.makedirs(self.data_path, exist_ok=True)
        if os.path.exists(DebugPath.BasePath()):
            shutil.rmtree(DebugPath.BasePath())
        os.makedirs(DebugPath.BasePath(), exist_ok=True)

    @staticmethod
    def _init_database():
        """
        初始化数据库
        """
        from src.models.base import db
        from src.models import all_models
        from playhouse.migrate import SqliteMigrator, migrate
        if db.is_closed():
            db.connect()
        db.create_tables(all_models)
        migrator = SqliteMigrator(db)
        for model in all_models:
            existing_columns = [c.name for c in db.get_columns(model._meta.table_name)]
            for field_name, field_obj in model._meta.fields.items():
                if field_name not in existing_columns:
                    logger.warning(f"Field '{field_name}' is missing in DB. Migrating...")
                    migrate(
                        migrator.add_column(model._meta.table_name, field_name, field_obj)
                    )
        db.close()
        from src.models.config import ConfigModel
        ConfigModel.update_database()
        logger.success("Database Initialized")

    @staticmethod
    def _load_game_database():
        from src.utils.game_database_tools import GakumasDatabase_ItemDataUtils, GakumasDatabase_ProduceCardDataUtils
        GakumasDatabase_ItemDataUtils()
        GakumasDatabase_ProduceCardDataUtils()
        logger.success("Load game database successfully")

    def _register_config_listening(self):

        def update_device(key, old, new):
            logger.warning(f"Reinitialize device......")
            suspend_task = self.task_queue.get_current_suspend_task()
            if suspend_task:
                self.task_queue.suspend_running_task()
            status = self.yolo_engine.running
            self.yolo_engine.stop()
            self.device = self.create_device_instance()
            self.yolo_engine.set_device(self.device)
            if status: self.yolo_engine.start()
            if suspend_task: self.task_queue.resume_suspended_task()
            return

        self.config_service.add_listener([
            "base.run_mode",
            "base.game_window_name",
            "base.adb_connect_mode",
            "base.adb_host",
            "base.adb_port",
            "base.adb_serial",
            "base.android_screen_capture_service",
            "base.android_touch_service",
            "base.game_package_name"
        ], update_device)

    @property
    def latest_frame(self):
        return self.yolo_engine.latest_frame

    @property
    def latest_results(self):
        return self.yolo_engine.latest_results

    def create_device_instance(self) -> Union[Android_App, Windows_App]:
        """
        创建设备操作实例
        """
        mode = self.config_service().base.run_mode.value.lower()
        if mode == DeviceType.PHONE:
            logger.debug("Initializing Android device")
            return Android_App()
        if mode == DeviceType.PC:
            logger.debug("Initializing Windows device")
            return Windows_App()
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

    def exec_task(self, task_name: str = None):
        return self.task_queue.start_queue(task_name)