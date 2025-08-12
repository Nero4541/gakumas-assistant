import ast
from datetime import datetime

from peewee import AutoField, CharField, BooleanField, DateTimeField

from src.utils.logger import logger
from src.models.base import BaseModel
from src.entity.Config import Config as ConfigEntity, ConfigItem


class ConfigModel(BaseModel):
    id = AutoField(primary_key=True)
    key = CharField(unique=True)
    value = CharField(default="")
    verify = CharField(unique=False, default=None)
    use_verify = BooleanField(default=False)
    last_modified_time = DateTimeField(default=datetime.now)

    @classmethod
    def load_config(cls) -> ConfigEntity:
        config = ConfigEntity()
        for row in cls.select():
            keys = row.key.split(".")
            if len(keys) != 2: # 跳过非法 key
                logger.warning(f"Skip load config: {row}")
                continue

            section_name, item_name = keys

            section = getattr(config, section_name, None)
            if section is None:
                logger.warning(f"Config entity not category: {section_name}")
                continue

            config_item: ConfigItem = getattr(section, item_name, None)
            if not isinstance(config_item, ConfigItem):
                continue

            try:
                cast_value = cls.cast_to_type(row.value, config_item.data_type)
            except Exception as e:
                logger.warning(f"Failed to cast value: {row.value}\n{e}")
                cast_value = config_item.default_value

            config_item.value = cast_value
            config_item.verify = row.verify
            config_item.use_verify = row.use_verify
            config_item.last_modified_time = row.last_modified_time

        return config

    @classmethod
    def save_config(cls, config_entity: ConfigEntity = ConfigEntity):
        for section_name in dir(config_entity):
            if section_name.startswith("__"):
                continue

            section = getattr(config_entity, section_name)
            for attr_name in dir(section):
                if attr_name.startswith("__"):
                    continue

                config_item = getattr(section, attr_name)
                if isinstance(config_item, ConfigItem):
                    key = f"{section_name}.{attr_name}"
                    if config_item.data_type == list:
                        config_item.value = list(set(config_item.value))
                    value_str = str(config_item.value)

                    config_row, created = cls.get_or_create(key=key, defaults={
                        'value': value_str,
                        'verify': config_item.verify or "",
                        'use_verify': config_item.use_verify or False,
                        'last_modified_time': datetime.now()
                    })
                    if not created:
                        config_row.value = value_str
                        config_row.verify = config_item.verify
                        config_row.use_verify = config_item.use_verify
                        config_row.last_modified_time = datetime.now()
                        config_row.save()

    @staticmethod
    def cast_to_type(value: str, target_type: type):
        if target_type == bool:
            return value.lower() in ("true", "1", "yes", "on")
        elif target_type == int:
            return int(value)
        elif target_type == float:
            return float(value)
        elif target_type in [dict, list, tuple]:
            return ast.literal_eval(value)
        elif target_type == str:
            return value
        else:
            raise ValueError(f"Unsupported cast type: {target_type}")


    @classmethod
    def init_config(cls):
        if len(cls().select()) >= 0:
            cls.save_config(ConfigEntity())
            return