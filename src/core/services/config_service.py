import threading
from copy import deepcopy, copy
from typing import Callable, Dict, List

from src.entity.Base import SingletonMeta
from src.utils.logger import logger
from src.models.config import ConfigModel
from src.entity.Config import Config, ConfigItem, _BaseConfigGroup


class _ConfigValueGroupProxy:
    """返回配置项 value 的只读/可赋值视图。"""

    def __init__(self, group: _BaseConfigGroup):
        object.__setattr__(self, "_group", group)

    def __getattr__(self, item):
        attr = getattr(object.__getattribute__(self, "_group"), item)
        if isinstance(attr, ConfigItem):
            return attr.value
        if isinstance(attr, _BaseConfigGroup):
            return _ConfigValueGroupProxy(attr)
        return attr

    def __setattr__(self, key, value):
        group = object.__getattribute__(self, "_group")
        attr = getattr(group, key, None)
        if isinstance(attr, ConfigItem):
            attr.set(value)
            return
        if isinstance(attr, _BaseConfigGroup):
            raise AttributeError(f"Cannot replace config group '{key}' directly")
        setattr(group, key, value)

    def __dir__(self):
        group = object.__getattribute__(self, "_group")
        return sorted(set(object.__dir__(self) + dir(group)))

    def __repr__(self):
        return repr(object.__getattribute__(self, "_group"))


class ConfigLoader(metaclass=SingletonMeta):
    _instance: 'ConfigLoader' = None
    _lock = threading.Lock()
    _last_save_config: Config = None

    def __init__(self):
        self.model = ConfigModel()

    def load(self) -> Config:
        if self.model.select().count() <= 0: # 如果没配置，则重置默认配置后返回
            self.reset()
        config = self.model.load_config()
        if self._last_save_config is None:
            self._last_save_config = self._copy_config()
        return config

    def save(self, config: Config):
        self.model.save_config(config)
        self._last_save_config = self._copy_config()

    def reset(self):
        self.model.delete().execute()
        self.model.save_config(Config())
        self._last_save_config = self._copy_config()

    def _copy_config(self):
        return deepcopy(self.model.load_config())

    @property
    def last_save(self):
        return copy(self._last_save_config)


class ConfigService(metaclass=SingletonMeta):
    def __init__(self):
        self._loader = ConfigLoader()
        self._config = None
        self._lock = threading.Lock()
        self._listeners: Dict[str, List[Callable[[str, object, object], None]]] = {}

    def get_config(self) -> Config:
        with self._lock:
            if self._config is None:
                self._config = self._loader.load()
            return self._config

    @property
    def items(self) -> Config:
        return self.get_config()

    def item(self, path: str) -> ConfigItem:
        return self.get_config().get_item(path)

    def save_config(self, new_config: Config = None):
        with self._lock:
            old_config = self._loader.last_save
            if new_config is not None:
                self._config = new_config
            # 保存到数据库
            self._loader.save(self._config)
            # 比较差异并通知监听器
        self._notify_diff(old_config, self._config)

    def reset_config(self):
        with self._lock:
            old_config = self._loader.last_save
            self._loader.reset()
            self._config = self._loader.load()
        self._notify_diff(old_config, self._config)

    def add_listener(self, keys: str | list[str], callback: Callable[[str, object, object], None]):
        """
        注册配置监听
        :param keys: "base.adb_host" / "base" / "*" 或 ["base.adb_host", "base"]
        :param callback: 回调函数，参数为 (key, old_value, new_value)
        """
        if isinstance(keys, str):
            keys = [keys]
        for key in keys:
            if key not in self._listeners:
                self._listeners[key] = []
            self._listeners[key].append(callback)
            logger.debug(f"Added config listener for {key}")

    def remove_listener(self, key: str, callback: Callable):
        """移除监听"""
        if key in self._listeners and callback in self._listeners[key]:
            self._listeners[key].remove(callback)

    def _notify_diff(self, old_config, new_config):
        """检测配置差异并通知监听者"""
        diff_items = self._find_diff_items(old_config, new_config)
        for key, (old_val, new_val) in diff_items.items():
            self._dispatch_event(key, old_val, new_val)

    @staticmethod
    def _find_diff_items(old: Config, new: Config) -> Dict[str, tuple]:
        """比较两个配置对象的差异"""
        diffs = {}
        for section_name in dir(old):
            if section_name.startswith("__"):
                continue
            section_old = getattr(old, section_name)
            section_new = getattr(new, section_name)
            if not (section_new and section_old):
                logger.debug(f"{'New' if section_new is None else 'Old'} Config obj Section {section_name} not found")
                continue
            for attr_name in dir(section_old):
                if attr_name.startswith("_"):
                    continue
                item_old = getattr(section_old, attr_name)
                item_new = getattr(section_new, attr_name)
                if hasattr(item_old, "value") and hasattr(item_new, "value"):
                    old_value = ConfigModel.cast_to_type(item_old.value, item_old.data_type)
                    if item_old.data_type == list:
                        if set(item_old.value) != set(item_new.value):
                            key = f"{section_name}.{attr_name}"
                            diffs[key] = (item_old.value, item_new.value)
                        continue
                    if old_value != item_new.value:
                        key = f"{section_name}.{attr_name}"
                        diffs[key] = (item_old.value, item_new.value)
        return diffs

    def _dispatch_event(self, key: str, old_val, new_val):
        """通知对应监听器"""
        logger.debug(f"Config changed: {key} = {old_val!r} → {new_val!r}")

        # 触发精准监听
        if key in self._listeners:
            for cb in self._listeners[key]:
                try:
                    cb(key, old_val, new_val)
                except Exception as e:
                    logger.error(f"Listener for {key} failed: {e}")

        # 触发分组监听
        section = key.split(".")[0]
        if section in self._listeners:
            for cb in self._listeners[section]:
                try:
                    cb(key, old_val, new_val)
                except Exception as e:
                    logger.error(f"Section listener {section} failed: {e}")

        # 触发全局监听
        if "*" in self._listeners:
            for cb in self._listeners["*"]:
                try:
                    cb(key, old_val, new_val)
                except Exception as e:
                    logger.error(f"Global listener failed: {e}")

    def __call__(self):
        return self.get_config()

    def __getattr__(self, item):
        config = self.get_config()
        if not hasattr(config, item):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{item}'")
        attr = getattr(config, item)
        if isinstance(attr, ConfigItem):
            return attr.value
        if isinstance(attr, _BaseConfigGroup):
            return _ConfigValueGroupProxy(attr)
        return attr

    def __dir__(self):
        return sorted(set(object.__dir__(self) + dir(self.get_config())))
