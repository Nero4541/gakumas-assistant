import json
import os
from dataclasses import dataclass
from typing import Any

from src.entity.Base import SingletonByFileMeta
from src.utils.logger import logger


class I18nJsonUtils(metaclass=SingletonByFileMeta):
    _file_path: str
    _data: list[dict[str, Any]]
    _id_index: dict[str, dict[str, Any]]  # 按 id 快速查找

    @dataclass
    class Result:
        id: str
        name: str
        description: str | None
        acquisitionRouteDescription: str | None

    def __init__(self, file_path: str):
        self._file_path = file_path
        self._id_index = {}
        if not os.path.exists(file_path):
            raise FileNotFoundError(file_path)
        self._load_json()

    def _load_json(self):
        with open(self._file_path, "r", encoding="utf-8") as f:
            content = json.load(f)
        self._data = content.get("data", [])
        # 构建 id 索引，便于快速查询
        for row in self._data:
            self._id_index[row["id"]] = row
        logger.info(f"[{self.__class__.__name__}] {len(self._data)} records loaded from {self._file_path}")

    def get_by_id(self, id: str) -> "Result":
        row = self._id_index.get(id)
        if not row:
            return None
        return self.Result(
            id=row.get("id"),
            name=row.get("name"),
            description=row.get("description"),
            acquisitionRouteDescription=row.get("acquisitionRouteDescription")
        )