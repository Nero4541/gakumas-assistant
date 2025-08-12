import threading

from src.entity.Base import SingletonMeta
from src.utils.logger import logger
from src.models.config import ConfigModel
from src.entity.Config import Config, ConfigVerifyError

class ConfigLoader(metaclass=SingletonMeta):
    _instance: 'ConfigLoader' = None
    _lock = threading.Lock()

    def __init__(self):
        self.model = ConfigModel()

    def load(self) -> Config:
        if self.model.select().count() <= 0: # 如果没配置，则重置默认配置后返回
            self.reset()
        return self.model.load_config()

    def save(self, config: Config):
        self.model.save_config(config)

    def reset(self):
        self.model.delete().execute()
        self.model.save_config(Config())

class ConfigService(metaclass=SingletonMeta):
    def __init__(self):
        self._loader = ConfigLoader()
        self._config = None
        self._lock = threading.Lock()

    def get_config(self) -> Config:
        with self._lock:
            if self._config is None:
                self._config = self._loader.load()
            return self._config

    def save_config(self, config: Config = None):
        with self._lock:
            if config is not None:
                self._config = config
            self._loader.save(self._config)

    def reset_config(self):
        with self._lock:
            self._loader.reset()
            self._config = self._loader.load()

    def __call__(self):
        return self.get_config()