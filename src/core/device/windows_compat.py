import platform
from typing import Any

_WINDOWS_APP_CLASS = None
_WINDOWS_IMPORT_ERROR = None

if platform.system() == "Windows":
    try:
        from src.core.device.Windows.app import Windows_App as _WINDOWS_APP_CLASS
    except Exception as exc:
        _WINDOWS_IMPORT_ERROR = exc


def windows_pc_mode_is_available() -> bool:
    return _WINDOWS_APP_CLASS is not None


def get_windows_unavailability_reason() -> str:
    if _WINDOWS_APP_CLASS is not None:
        return ""
    if platform.system() != "Windows":
        return "PC 模式仅支持 Windows，请在 macOS/Linux 上使用 Phone 模式。"
    if _WINDOWS_IMPORT_ERROR is not None:
        return (
            "PC 模式依赖的 Windows 专用组件未就绪（通常是 pywin32 未安装或损坏），"
            "请重新执行 `pip install -r requirements.txt` 后重试。"
        )
    return "PC 模式当前不可用。"


def create_windows_device():
    if _WINDOWS_APP_CLASS is None:
        message = get_windows_unavailability_reason()
        if _WINDOWS_IMPORT_ERROR is not None:
            raise RuntimeError(message) from _WINDOWS_IMPORT_ERROR
        raise RuntimeError(message)
    return _WINDOWS_APP_CLASS()


def is_windows_device(device: Any) -> bool:
    return _WINDOWS_APP_CLASS is not None and isinstance(device, _WINDOWS_APP_CLASS)
