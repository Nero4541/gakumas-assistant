import os.path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.constants.data_path import DataPath
from src.core.Web.websocket import WebSocketManager
from time import sleep
from typing import TYPE_CHECKING

from src.models import ConfigModel
from src.utils.diff_tools import GakumasuDiffItemDataUtils
from src.utils.i18n_tools import I18nJsonUtils

if TYPE_CHECKING:
    from src.main import AppProcessor

def _api_return(status: bool, message: str = '', data: dict | list = None):
    return {
        'status': status,
        'message': message,
        'data': data
    }

def register_routes(app: FastAPI, processor: "AppProcessor", ws_manager: WebSocketManager):
    item_db = GakumasuDiffItemDataUtils(DataPath.GakumasuDiffData.ITEM)
    item_translation = I18nJsonUtils(DataPath.GakumasTranslationData.ITEM)
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await ws_manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)

    @app.get("/api/start")
    def start_task_queue():
        processor.exec_task()
        return _api_return(True, "OK")

    @app.get("/api/run_task/{task_name:str}")
    def run_task(task_name: str):
        processor.exec_task(task_name)
        return _api_return(True, "OK")

    @app.get("/api/stop")
    def stop_task_queue():
        processor.task_queue.stop()
        return _api_return(True, "OK")

    @app.get("/api/status")
    def get_status():
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

    @app.get("/api/get_registered_tasks")
    def get_registered_tasks():
        return _api_return(True, 'OK', processor.task_queue.get_task_list())

    @app.post("/api/disable_task/{task_name:str}")
    def disable_task(task_name):
        new_config = processor.config_service().base.disabled_tasks.value.append(task_name)
        processor.config_service.save_config(new_config)
        return _api_return(True, 'OK', processor.task_queue.disable_task(task_name))

    @app.post("/api/enable_task/{task_name:str}")
    def enable_task(task_name):
        new_config = processor.config_service().base.disabled_tasks.value.remove(task_name)
        processor.config_service.save_config(new_config)
        return _api_return(True, 'OK', processor.task_queue.enable_task(task_name))

    @app.get("/api/switch_yolo_model/{model_name:str}")
    def switch_yolo_model(model: str):
        model_list = ["base_ui", "producer"]
        if model.lower() not in model_list:
            return _api_return(False, "Invalid model name")
        processor.yolo_engine.load_model(model.upper())
        return _api_return(True, f"model switched to {model}")

    @app.get("/api/config")
    def get_all_config():
        config = processor.config_service()
        return _api_return(True, 'OK', config.to_json_dict())

    @app.get("/api/config/{task_name:str}")
    def get_task_config(task_name: str):
        if task_name not in processor.task_queue.get_task_list().keys():
            return _api_return(False, "Invalid task name")
        all_config = processor.config_service().to_json_dict()
        task_name = f"task__{task_name}"
        if task_name not in all_config.keys():
            return _api_return(False, "The task does not have any configuration.")
        return _api_return(True, "OK", all_config[task_name])

    @app.put("/api/config")
    async def set_all_config(request: Request):
        data = await request.json()
        config = processor.config_service()
        status, errors = config.from_json_dict(data)
        if status:
            processor.config_service.save_config(config)
            return _api_return(True, 'OK', config.to_json_dict())
        else:
            return _api_return(False, "error", {f"{e.section}.{e.field}": e.message for e in errors})

    @app.put("/api/config/{task_name:str}")
    async def set_task_config(request: Request, task_name: str):
        if task_name not in processor.task_queue.get_task_list().keys():
            return _api_return(False, "Invalid task name")
        config = processor.config_service()
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

    @app.get("/api/item/list")
    def get_all_items():
        items = item_db.get_all_item()
        all_items = []
        for item in items:
            translation = item_translation.get_by_id(item.id)
            all_items.append({
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "acquisitionRouteDescription": item.acquisitionRouteDescription,
                "translation": {
                    "name": translation.name,
                    "description": translation.description,
                    "acquisitionRouteDescription": translation.acquisitionRouteDescription,
                } if translation else {},
                "image": os.path.exists(os.path.join(processor.data_path, f"CLIP/items/{item.id}.png")),
            })
        return _api_return(True, "OK", all_items)

    app.mount("/assets", StaticFiles(directory="dist/assets", html=True), name="static")
    app.mount("/api/clip_image", StaticFiles(directory="data/CLIP", html=False), name="clip_images")

    @app.get("/")
    def read_index():
        return FileResponse("dist/index.html")
