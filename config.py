from src.constants.yolo.model_type import YoloModelType

# Web服务器监听地址
web_server_host: str = "127.0.0.1"
# Web服务器监听端口
web_server_port: int = 8000
# 是否自动打开浏览器
auto_open_web_browser: bool = False
# 是否自动重载服务器
auto_reload_server: bool = False
# 是否启用Debug模式
debug: bool = True

model_config = {
    YoloModelType.BASE_UI: {
        "model_path": "model/base_ui.onnx",
        "conf_threshold": 0.5,
        "iou_threshold": 0.5
    },
    YoloModelType.PRODUCER: {
        "model_path": "model/producer.onnx",
        "conf_threshold": 0.5,
        "iou_threshold": 0.5
    },
}