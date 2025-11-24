import asyncio
import os.path
import threading
from contextlib import asynccontextmanager
from time import sleep

import uvicorn
import webview
from fastapi import FastAPI

from src.core.web.routers import register_routes
from src.utils.args import args
from src.main import AppProcessor

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def start_webapp(core_processor: AppProcessor):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        core_processor.ws_manager.set_fastapi_loop(asyncio.get_event_loop())
        yield
        pass
    webapp = FastAPI(lifespan=lifespan)
    register_routes(webapp, core_processor, processor.ws_manager)
    uvicorn.run(
        webapp,
        host=args.host,
        port=args.port,
        log_level="info" if args.http_server_info else "warning",
        reload=False
    )

if __name__ == "__main__":
    processor = AppProcessor()
    webapp_thread = threading.Thread(target=start_webapp, args=(processor,), daemon=True)
    webapp_thread.start()
    processor.yolo_engine.start()
    if not args.not_use_webview:
        window = webview.create_window(
            'Gakumas Assistant',
            f'http://{args.host}:{args.port}',
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
    else:
        try:
            from src.utils.logger import logger
            logger.success(f"Server started at http://{args.host}:{args.port}")
            while True:
                sleep(0.1)
        except KeyboardInterrupt:
            processor.yolo_engine.stop()
            exit(0)