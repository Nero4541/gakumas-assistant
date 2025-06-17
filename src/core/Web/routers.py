from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import config
from src.core.Web.websocket import WebSocketManager
from time import sleep
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app import AppProcessor


def _api_return(status: bool, message: str = '', data: dict = None):
    return {
        'status': status,
        'message': message,
        'data': data
    }


def register_routes(app: FastAPI, processor: "AppProcessor", ws_manager: WebSocketManager):
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

    @app.get("/api/stop")
    def stop_task_queue():
        processor.task_queue.stop()
        return _api_return(True, "OK")

    @app.get("/api/status")
    def get_status():
        return _api_return(True, 'OK', {
            'platform': config.mode.lower(),
            'yolo': processor.running,
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
        return _api_return(True, 'OK', processor.task_queue.disable_task(task_name))

    @app.post("/api/enable_task/{task_name:str}")
    def enable_task(task_name):
        return _api_return(True, 'OK', processor.task_queue.enable_task(task_name))

    @app.get("/api/switch_yolo_model/{model_name:str}")
    def switch_yolo_model(model: str):
        model_list = ["base_ui", "producer"]
        if model.lower() not in model_list:
            return _api_return(False, "Invalid model name")
        processor.load_model(model.upper())
        return _api_return(True, f"model switched to {model}")

    app.mount("/assets", StaticFiles(directory="dist/assets", html=True), name="static")

    @app.get("/")
    def read_index():
        return FileResponse("dist/index.html")
