import json
import os.path
from copy import copy

import adbutils
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.constants.path.data_path import DataPath
from src.constants.websocket_actions import WebsocketActions
from src.core.web.websocket import WebSocketManager
from typing import TYPE_CHECKING

from src.entity.Config import Config
from src.utils.dmm_tools import extract_gakumas_launch_parameters
from src.utils.game_database_tools import GakumasDatabase_ItemDataUtils
from src.utils.opencv_tools import get_black_image
from src.utils.logger import logger

if TYPE_CHECKING:
    from src.main import AppProcessor

def _api_return(status: bool, message: str = '', data: dict | list = None):
    return {
        'status': status,
        'message': message,
        'data': data
    }

def register_routes(app: FastAPI, processor: "AppProcessor", ws_manager: WebSocketManager):
    item_db = GakumasDatabase_ItemDataUtils(DataPath.GakumasuDiffData.ITEM)
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await ws_manager.connect(websocket)
        await asyncio.sleep(1)
        try:
            await websocket.send_bytes(f"{640},{640}".encode('utf-8') + b"," + get_black_image((640, 640)))
            while True:
                data = await websocket.receive_json()
                if not data.get("action"):
                    continue
                action = data.get("action")
                data = data.get("data")
                if action == WebsocketActions.BaseActionFlag + ":" + WebsocketActions.WebsocketHeartBeat.Ping:
                    await ws_manager.send_action(websocket, WebsocketActions.WebsocketHeartBeat.Pong)
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)
        except Exception as e:
            logger.error(f"Websocket Error: {e}")

    @app.get("/api/task/start")
    def start_task_queue():
        """启动任务队列"""
        processor.exec_task()
        return _api_return(True, "OK")

    @app.get("/api/task/start/{task_name:str}")
    def run_task(task_name: str):
        """
        运行任务（单个）
        :param task_name: 任务名
        :return:
        """
        processor.exec_task(task_name)
        return _api_return(True, "OK")

    @app.get("/api/task/stop")
    def stop_task_queue():
        """停止任务队列"""
        processor.task_queue.stop()
        return _api_return(True, "OK")

    @app.get("/api/status")
    def get_status():
        """获取服务状态"""
        return _api_return(True, 'OK', {
            'platform': processor.config_service().base.run_mode.value.lower(),
            'yolo': processor.yolo_engine.running,
            'task': processor.task_queue.queue_status(),
            'game': {
                'current_location': processor.game_status_manager.current_location,
                'player': {
                    'level': processor.game_status_manager.player.level,
                    'gem': processor.game_status_manager.player.gem,
                    'stamina': processor.game_status_manager.player.stamina,
                }
            }
        })

    @app.get("/api/task/get_registered_tasks")
    def get_registered_tasks():
        """获取所有已注册的任务"""
        return _api_return(True, 'OK', processor.task_queue.get_task_list())

    @app.post("/api/task/disable/{task_name:str}")
    def disable_task(task_name):
        """
        禁用任务
        :param task_name: 任务id
        :return:
        """
        new_config = processor.config_service().base.disabled_tasks.value.append(task_name)
        processor.config_service.save_config(new_config)
        return _api_return(True, 'OK', processor.task_queue.disable_task(task_name))

    @app.post("/api/task/enable/{task_name:str}")
    def enable_task(task_name):
        """
        启用任务
        :param task_name: 任务id
        :return:
        """
        new_config = processor.config_service().base.disabled_tasks.value.remove(task_name)
        processor.config_service.save_config(new_config)
        return _api_return(True, 'OK', processor.task_queue.enable_task(task_name))

    # @app.get("/api/debug/switch_yolo_model/{model_name:str}")
    # def switch_yolo_model(model: str):
    #     model_list = ["base_ui", "producer"]
    #     if model.lower() not in model_list:
    #         return _api_return(False, "Invalid model name")
    #     processor.yolo_engine.load_model(model.upper())
    #     return _api_return(True, f"model switched to {model}")

    @app.get("/api/config")
    def get_all_config():
        """
        获取所有配置
        :return:
        """
        config = processor.config_service()
        return _api_return(True, 'OK', config.to_json_dict())

    @app.get("/api/config/tools/reset_config")
    def reset_config():
        """
        重置所有配置
        :return:
        """
        processor.config_service.reset_config()
        return get_all_config()

    @app.get("/api/config/tools/refresh_ddm_token")
    def refresh_ddm_token():
        """刷新DDMPlayer Token"""
        ddm_cfg = processor.config_service().dmm_player
        try:
            result = extract_gakumas_launch_parameters()
            ddm_cfg.game_exe_path.value = result.exe_path
            ddm_cfg.viewer_id.value = result.viewer_id
            ddm_cfg.open_id.value = result.open_id
            ddm_cfg.pf_token.value = result.pf_token
            processor.config_service.save_config()
        except Exception as e:
            return _api_return(False, f"提取游戏启动参数失败 {e}")
        return _api_return(True, "OK")

    @app.get("/api/config/{task_name:str}")
    def get_task_config(task_name: str):
        """
        获取单个任务配置
        :param task_name: 任务id
        :return:
        """
        if task_name not in processor.task_queue.get_task_list().keys():
            return _api_return(False, "Invalid task name")
        all_config = processor.config_service().to_json_dict()
        task_name = f"task__{task_name}"
        if task_name not in all_config.keys():
            return _api_return(False, "The task does not have any configuration.")
        return _api_return(True, "OK", all_config[task_name])

    @app.put("/api/config")
    async def set_all_config(request: Request):
        """
        保存所有任务配置
        :param request:
        :return:
        """
        data = await request.json()
        config = copy(processor.config_service())
        status, errors = config.from_json_dict(data)
        if status:
            processor.config_service.save_config(config)
            return _api_return(True, 'OK', config.to_json_dict())
        else:
            return _api_return(False, "error", {f"{e.section}.{e.field}": e.message for e in errors})

    @app.put("/api/config/{task_name:str}")
    async def set_task_config(request: Request, task_name: str):
        """
        保存单个任务配置
        :param request:
        :param task_name: 任务id
        :return:
        """
        if task_name not in processor.task_queue.get_task_list().keys():
            return _api_return(False, "Invalid task name")
        config = copy(processor.config_service())
        all_config = config.to_json_dict()
        task_name = f"task__{task_name}"
        if task_name not in all_config.keys():
            return _api_return(False, "The task does not have any configuration.")
        data = await request.json()
        # 合并新的 task 配置
        all_config[task_name] = data
        status, errors = config.from_json_dict(all_config)
        if status:
            processor.config_service.save_config(config)
            return _api_return(True, 'OK', config.to_json_dict()[task_name])
        else:
            return _api_return(False, "error", {f"{e.section}.{e.field}": e.message for e in errors})

    @app.get("/api/adb/devices")
    def get_adb_devices():
        """获取所有ADB设备"""
        return _api_return(True, 'OK', {
            "devices": [s.serial for s in adbutils.adb.device_list()],
        })

    @app.get("/api/adb/devices/usb")
    def get_adb_usb_serial_list():
        """获取使用USB连接的ADB设备"""
        serial_list = adbutils.adb.device_list()
        serial_list = [s.serial for s in serial_list if ":" not in str(s.serial)]
        return _api_return(True, 'OK', {
            "devices": serial_list,
        })

    @app.get("/api/item/list")
    def get_all_items():
        """获取所有物品列表"""
        items = item_db.get_all_item()
        all_items = []
        for item in items:
            all_items.append({
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "acquisitionRouteDescription": item.acquisitionRouteDescription,
                "translation": {
                    "name": item.localization.name,
                    "description": item.localization.description,
                    "acquisitionRouteDescription": item.localization.acquisitionRouteDescription,
                } if item.localization else {},
                "image": os.path.exists(os.path.join(processor.data_path, f"CLIP/items/{item.id}.png")),
            })
        return _api_return(True, "OK", all_items)

    app.mount("/assets", StaticFiles(directory="dist/assets", html=True), name="static")
    app.mount("/api/clip_image", StaticFiles(directory="data/CLIP", html=False), name="clip_images")

    @app.get("/")
    def read_index():
        return FileResponse("dist/index.html")
