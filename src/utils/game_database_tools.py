import dataclasses
import json
import os
import re
import threading
from dataclasses import dataclass
from typing import Any, TextIO, List, Dict, Optional, Tuple

import yaml

from src.entity.Game.Database.General import GeneralProduceDescriptionsLocalization
from src.entity.Game.Database.Item import Item, ItemLocalization
from src.entity.Game.Database.ProduceCard import ProduceCard, ProduceCardLocalization
from src.entity.Game.Database.ProduceCardGrowEffect import ProduceCardGrowEffect
from src.entity.Game.Database.ProduceExamEffect import ProduceExamEffect
from src.entity.Game.Database.ProduceExamTrigger import ProduceExamTrigger
from src.utils.string_tools import string_match, MatchConfig
from src.utils.logger import logger
from src.constants.path.data_path import DataPath

class _SingletonByFileMeta(type):
    _instances = {}
    _lock = threading.RLock()

    def __call__(cls, data_file=None, *args, **kwargs):
        if data_file is None:
            # 取类本身的默认值，而不是强迫用户传
            data_file = cls.__init__.__defaults__[0]
        print(data_file)
        key = (cls, os.path.abspath(data_file))  # 用绝对路径作为 key
        if key not in cls._instances:
            with cls._lock:
                if key not in cls._instances:
                    cls._instances[key] = super().__call__(data_file, *args, **kwargs)
        return cls._instances[key]

class _BaseYamlDatabase(metaclass=_SingletonByFileMeta):
    data_cls = None     # dataclass 类型，由子类指定
    loc_cls = None      # localization dataclass 类型，由子类指定
    key_builder = None  # 如何构建 map key（支持 id 或 id.level）
    _diff_file:str = None
    _data: List[Any] = None
    _map: Dict[str, Any] = None


    def __init__(self, data_file):
        self._diff_file = data_file
        if not os.path.exists(data_file):
            raise FileNotFoundError(data_file)
        self._load_database()

    @classmethod
    @logger.catch
    def _from_dict(cls, target_dataclass, data):
        """
        将Dict数据转换到dataclass
        :param target_dataclass: 目标dataclass
        :param data: 数据字典
        :return:
        """
        if not hasattr(target_dataclass, "__dataclass_fields__"):
            return data

        kwargs = {}
        for f_name, f_type in target_dataclass.__annotations__.items():
            value = data.get(f_name, dataclasses.MISSING)

            if value is dataclasses.MISSING:
                continue

            # List[T]
            if getattr(f_type, "__origin__", None) is list:
                inner = f_type.__args__[0]
                if value is None:
                    kwargs[f_name] = []
                else:
                    kwargs[f_name] = [cls._from_dict(inner, v) for v in value]

            elif hasattr(f_type, "__dataclass_fields__"):
                kwargs[f_name] = cls._from_dict(f_type, value)

            else:
                kwargs[f_name] = value

        return target_dataclass(**kwargs)

    @classmethod
    def _preprocess_yaml_data(cls, f: TextIO) -> str:
        _content = f.read()
        _content = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", _content)
        _content = _content.replace('\t', '    ')
        return _content

    @classmethod
    def _load_localization(cls, data_file_path, data_entity):
        with open(os.path.join(DataPath.GakumasTranslationData.BASE, f"{os.path.splitext(os.path.basename(data_file_path))[0]}.json"), "r", encoding="utf-8") as f:
            entries = json.load(f)
            for entry in entries.get("data", []):
                if pd := entry.get("produceDescriptions"):
                    entry["produceDescriptions"] = [
                        d for d in pd if isinstance(d, dict)
                    ]
            objects = [cls._from_dict(data_entity, entry) for entry in entries.get("data", [])]
        return objects

    def _load_yaml(self) -> list[dict]:
        """
        加载yaml文件
        :return:
        """
        with open(self._diff_file, "r", encoding="utf-8") as f:
            content = self._preprocess_yaml_data(f)
        return yaml.load(content, Loader=yaml.CSafeLoader)

    def _load_objects(self, entries) -> list:
        """
        加载数据到对象
        :param entries:
        :return:
        """
        return [self._from_dict(self.data_cls, entry) for entry in entries]

    def _load_localization_data(self):
        """
        加载本地化数据
        :return:
        """
        if not self.loc_cls:
            return {}
        locs = self._load_localization(self._diff_file, self.loc_cls)
        return self._build_loc_map(locs)

    def _build_loc_map(self, loc_objects):
        """
        构建本地化映射
        :param loc_objects:
        :return:
        """
        return {o.id: o for o in loc_objects}

    def _build_map_key(self, obj):
        """
        构建数据id映射
        :param obj:
        :return:
        """
        return getattr(obj, "id")

    def _load_database(self):
        entries = self._load_yaml()
        objects = self._load_objects(entries)
        loc_map = self._load_localization_data()

        for obj in objects:
            if self.loc_cls:
                obj.localization = loc_map.get(self._build_map_key(obj))

        self._data = objects
        self._map = {self._build_map_key(o): o for o in objects}

        logger.info(
            f"[{self.__class__.__name__}] {len(self._data)} records loaded from {self._diff_file}"
        )

    def get_all_item(self):
        return self._data

    def get_map(self):
        return self._map

    def get_by_id(self, id):
        return self._map.get(id)

# class GakumasDatabaseItemDataUtils(metaclass=SingletonByFileMeta):
#     _diff_file: str
#     _data: list[dict[str, Any]]
#     _names:list[str] = []
#
#     @dataclass
#     class Result:
#         id: str | None
#         name: str
#         description: str | None
#         acquisitionRouteDescription: str | None
#
#     def __init__(self, data_file = DataPath.GakumasuDiffData.ITEM):
#         self._diff_file = data_file
#         if not os.path.exists(data_file):
#             FileNotFoundError(data_file)
#         self._load_database()
#
#     def _load_database(self):
#         with open(self._diff_file, "r", encoding="utf-8") as f:
#             self._data = yaml.safe_load(f)
#         logger.info(f"[{self.__class__.__name__}] {len(self._data)} records have been loaded from the {self._diff_file} file")
#         for row in self._data:
#             self._names.append(row["name"])
#
#     def search(self, ocr_result, match_config: MatchConfig = None):
#         result = string_match(ocr_result, self._names, match_config)
#         if not result:
#             return False, self.Result(None, ocr_result, None, None)
#         data = self._data[self._names.index(result.result)]
#         return True, self.Result(data["id"], result.result, data["description"], data["acquisitionRouteDescription"])
#
#     def get_by_id(self, id: str) -> "Result":
#         for index, row in enumerate(self._data):
#             if row["id"] == id:
#                 return self.Result(row["id"], row["name"], row["description"], row["acquisitionRouteDescription"])
#         return False
#
#     def get_by_name(self, name: str) -> "Result":
#         for index, row in enumerate(self._data):
#             if row["name"] == name:
#                 return self.Result(row["id"], row["name"], row["description"], row["acquisitionRouteDescription"])
#         return False
#
#     def get_all_item(self):
#         return [self.Result(row["id"], row["name"], row["description"], row["acquisitionRouteDescription"]) for row in self._data]

class GakumasDatabase_ItemDataUtils(_BaseYamlDatabase):
    data_cls = Item
    loc_cls = ItemLocalization

    def __init__(self, data_file = DataPath.GakumasuDiffData.ITEM):
        super().__init__(data_file)

    def search(self, ocr_result, match_config=None):
        name_map = {c.name: c for c in self._data}
        result = string_match(ocr_result, list(name_map.keys()), match_config)
        if not result:
            return False, None
        return True, name_map[result.result]

class GakumasDatabase_ExamTriggerDataUtils(_BaseYamlDatabase):
    data_cls = ProduceExamTrigger
    loc_cls = GeneralProduceDescriptionsLocalization

    def __init__(self, data_file=DataPath.GakumasuDiffData.EXAM_TRIGGER):
        super().__init__(data_file)

class GakumasDatabase_ExamEffectDataUtils(_BaseYamlDatabase):
    data_cls = ProduceExamEffect
    loc_cls = GeneralProduceDescriptionsLocalization

    def __init__(self, data_file=DataPath.GakumasuDiffData.EXAM_EFFECT):
        super().__init__(data_file)

class GakumasDatabase_GrowEffectDataUtils(_BaseYamlDatabase):
    data_cls = ProduceCardGrowEffect
    loc_cls = None

    def _load_database(self):
        super()._load_database()

        exam_triggers = GakumasDatabase_ExamTriggerDataUtils()
        for ge in self._data:
            ge.playProduceExamTriggerCls = exam_triggers.get_by_id(ge.playProduceExamTriggerId)
            ge.playEffectProduceExamTriggerCls = exam_triggers.get_by_id(ge.playEffectProduceExamTriggerId)
            for i, tid in enumerate(ge.targetPlayEffectProduceExamTriggerIds):
                ge.targetPlayEffectProduceExamTriggerClss[i] = exam_triggers.get_by_id(tid)

class GakumasDatabase_ProduceCardDataUtils(_BaseYamlDatabase):
    data_cls = ProduceCard
    loc_cls = ProduceCardLocalization

    def _build_map_key(self, card):
        return f"{card.id}.{card.upgradeCount}"

    def _build_loc_map(self, loc_objects):
        return {f"{o.id}.{o.upgradeCount}": o for o in loc_objects}

    def _load_database(self):
        super()._load_database()

        exam_effect = GakumasDatabase_ExamEffectDataUtils()
        exam_trigger = GakumasDatabase_ExamTriggerDataUtils()

        for card in self._data:
            # 补全 Effect & Trigger 指针
            for e in card.playEffects:
                if e.produceExamTriggerId:
                    e.produceExamTriggerCls = exam_trigger.get_by_id(e.produceExamTriggerId)
                if e.produceExamEffectId:
                    e.produceExamEffectCls = exam_effect.get_by_id(e.produceExamEffectId)

            card.playProduceExamTriggerCls = exam_trigger.get_by_id(card.playProduceExamTriggerId)

    def search(self, ocr_result, match_config=None):
        name_map = {c.name: c for c in self._data}
        result = string_match(ocr_result, list(name_map.keys()), match_config)
        if not result:
            return False, None
        return True, name_map[result.result]