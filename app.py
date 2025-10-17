import os.path
import threading
from time import sleep

import uvicorn
import webview
from fastapi import FastAPI

import config
from src.core.Web.routers import register_routes
from src.main import AppProcessor


def start_webapp(core_processor: AppProcessor):
    webapp = FastAPI()
    register_routes(webapp, core_processor, processor.ws_manager)
    uvicorn.run(
        webapp,
        host=config.web_server_host,
        port=config.web_server_port,
        log_level="warning",
        reload=False
    )

if __name__ == "__main__":
    processor = AppProcessor()
    webapp_thread = threading.Thread(target=start_webapp, args=(processor,), daemon=True)
    webapp_thread.start()
    processor.yolo_engine.start()
    window = webview.create_window(
        'Gakumas Assistant',
        f'http://localhost:{config.web_server_port}',
        width=1200,
        height=800,
        frameless=True,
        shadow=True,
        easy_drag=True,
        text_select=True
    )
    webview.start(icon=os.path.join(os.getcwd(), "assets","images","gakumas_logo.png"))
    processor.yolo_engine.stop()
    exit(0)
    # try:
    #     while True:
    #         sleep(0.1)
    # except KeyboardInterrupt:
    #     processor.yolo_engine.stop()
    #     exit(0)