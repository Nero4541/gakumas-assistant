import os
from dataclasses import dataclass
from typing import Any

import yaml

from src.entity.Base import SingletonByFileMeta
from src.utils.string_tools import string_match, MatchConfig
from src.utils.logger import logger

class GakumasuDiffItemDataUtils(metaclass=SingletonByFileMeta):
    _diff_file: str
    _data: list[dict[str, Any]]
    _names:list[str] = []

    @dataclass
    class Result:
        id: str | None
        name: str
        description: str | None
        acquisitionRouteDescription: str | None

    def __init__(self, diff_file):
        self._diff_file = diff_file
        if not os.path.exists(diff_file):
            FileNotFoundError(diff_file)
        self._load_diff()

    def _load_diff(self):
        with open(self._diff_file, "r", encoding="utf-8") as f:
            self._data = yaml.safe_load(f)
        logger.info(f"[{self.__class__.__name__}] {len(self._data)} records have been loaded from the {self._diff_file} file")
        for row in self._data:
            self._names.append(row["name"])

    def search(self, ocr_result, match_config: MatchConfig = None):
        result = string_match(ocr_result, self._names, match_config)
        if not result:
            return False, self.Result(None, ocr_result, None, None)
        data = self._data[self._names.index(result.result)]
        return True, self.Result(data["id"], result.result, data["description"], data["acquisitionRouteDescription"])

    def get_by_id(self, id: str) -> "Result":
        for index, row in enumerate(self._data):
            if row["id"] == id:
                return self.Result(row["id"], row["name"], row["description"], row["acquisitionRouteDescription"])
        return False

    def get_by_name(self, name: str) -> "Result":
        for index, row in enumerate(self._data):
            if row["name"] == name:
                return self.Result(row["id"], row["name"], row["description"], row["acquisitionRouteDescription"])
        return False

    def get_all_item(self):
        return [self.Result(row["id"], row["name"], row["description"], row["acquisitionRouteDescription"]) for row in self._data]