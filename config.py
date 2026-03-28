from src.constants.yolo.model_type import YoloModelType
from src.utils.runtime_paths import resolve_runtime_str

model_config = {
    YoloModelType.BASE_UI: resolve_runtime_str("model", "base_ui.onnx"),
    YoloModelType.PRODUCER: resolve_runtime_str("model", "producer.onnx"),
}
