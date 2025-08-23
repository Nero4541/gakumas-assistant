import os
import threading


class SingletonMeta(type):
    _instances = {}
    _lock = threading.Lock()
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]

class SingletonByFileMeta(type):
    _instances = {}
    _lock = threading.Lock()

    def __call__(cls, diff_file, *args, **kwargs):
        key = (cls, os.path.abspath(diff_file))  # 用绝对路径作为 key
        if key not in cls._instances:
            with cls._lock:
                if key not in cls._instances:
                    cls._instances[key] = super().__call__(diff_file, *args, **kwargs)
        return cls._instances[key]