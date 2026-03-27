import asyncio
import os.path
import platform
import sys
import threading
import webbrowser
from contextlib import asynccontextmanager
import io
from time import sleep

import uvicorn
from fastapi import FastAPI

from src.core.web.routers import register_routes
from src.utils.logger import logger
from src.utils.args import args
from src.main import AppProcessor

try:
    import webview as WEBVIEW_MODULE
except Exception as exc:
    WEBVIEW_MODULE = None
    WEBVIEW_IMPORT_ERROR = exc
else:
    WEBVIEW_IMPORT_ERROR = None

PYWEBVIEW_WINDOW_BRIDGE = None

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


class PyWebviewWindowBridge:
    def __init__(self):
        self.window = None
        self._maximized = False
        self._normal_bounds = None

    def bind_window(self, window):
        self.window = window
        self._maximized = False
        self._normal_bounds = None

    def _capture_bounds(self):
        if self.window is None:
            return None
        return {
            "x": int(self.window.x),
            "y": int(self.window.y),
            "width": int(self.window.width),
            "height": int(self.window.height),
        }

    def _apply_bounds(self, bounds):
        if self.window is None or not bounds:
            return
        self.window.resize(int(bounds["width"]), int(bounds["height"]))
        self.window.move(int(bounds["x"]), int(bounds["y"]))

    def get_window_state(self):
        return {
            "frameless": bool(getattr(self.window, "frameless", False)),
            "maximized": self._maximized,
        }

    def minimize_window(self):
        if self.window is not None:
            self.window.minimize()
        return self.get_window_state()

    def toggle_maximize_window(self):
        if self.window is None:
            return self.get_window_state()
        if platform.system() == "Darwin":
            if self._maximized:
                self._apply_bounds(self._normal_bounds)
            else:
                screen = getattr(self.window, "screen", None)
                self._normal_bounds = self._capture_bounds()
                if screen is None:
                    self.window.maximize()
                else:
                    self.window.resize(int(screen.width), int(screen.height))
                    self.window.move(int(screen.x), int(screen.y))
            self._maximized = not self._maximized
            return self.get_window_state()
        if self._maximized:
            self.window.restore()
        else:
            self.window.maximize()
        self._maximized = not self._maximized
        return self.get_window_state()

    def close_window(self):
        if self.window is not None:
            threading.Timer(0.1, self.window.destroy).start()
        return {"closing": True}


def start_webapp(core_processor: AppProcessor):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        core_processor.ws_manager.set_fastapi_loop(asyncio.get_event_loop())
        core_processor.start_background_services()
        yield
        pass
    webapp = FastAPI(lifespan=lifespan)
    register_routes(webapp, core_processor, core_processor.ws_manager)
    uvicorn.run(
        webapp,
        host=args.host,
        port=args.port,
        log_level="info" if args.http_server_info else "warning",
        reload=False
    )


def _start_native_webview(url: str):
    global PYWEBVIEW_WINDOW_BRIDGE
    if WEBVIEW_MODULE is None:
        raise RuntimeError("pywebview is unavailable") from WEBVIEW_IMPORT_ERROR

    window_options = {
        "width": 1200,
        "height": 800,
        "text_select": True,
    }
    if platform.system() in {"Windows", "Darwin"}:
        window_options.update(
            {
                "frameless": True,
                "shadow": True,
                "easy_drag": False,
            }
        )
    if platform.system() == "Windows":
        window_options["easy_drag"] = True

    PYWEBVIEW_WINDOW_BRIDGE = PyWebviewWindowBridge()
    window_options["js_api"] = PYWEBVIEW_WINDOW_BRIDGE

    window = WEBVIEW_MODULE.create_window("Gakumas Assistant", url, **window_options)
    PYWEBVIEW_WINDOW_BRIDGE.bind_window(window)
    icon_path = os.path.join(os.getcwd(), "assets", "images", "gakumas_logo.png")
    start_kwargs = {}
    if os.path.exists(icon_path):
        start_kwargs["icon"] = icon_path
    WEBVIEW_MODULE.start(**start_kwargs)


def _run_server_forever(url: str, processor: AppProcessor, open_browser: bool = False):
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception as exc:
            logger.warning(f"Open browser failed: {exc}")
    logger.success(f"Server started at {url}")
    try:
        while True:
            sleep(0.1)
    except KeyboardInterrupt:
        processor.yolo_engine.stop()
        raise SystemExit(0)

if __name__ == "__main__":
    processor = AppProcessor()
    webapp_thread = threading.Thread(target=start_webapp, args=(processor,), daemon=True)
    webapp_thread.start()
    processor.start_inference_if_possible()
    server_url = f"http://{args.host}:{args.port}"
    if not args.not_use_webview:
        try:
            _start_native_webview(server_url)
            processor.yolo_engine.stop()
            raise SystemExit(0)
        except Exception as exc:
            logger.warning(f"Native webview unavailable, fallback to browser mode: {exc}")
            _run_server_forever(server_url, processor, open_browser=True)
    else:
        _run_server_forever(server_url, processor)
