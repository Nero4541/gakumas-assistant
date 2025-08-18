import os
from dataclasses import dataclass
from typing import Any

import yaml

from src.utils.string_tools import string_match, MatchConfig
from src.utils.logger import logger

class GakumasuDiffItemDataUtils:
    _diff_file: str
    _data: list[dict[str, Any]]
    _names:list[str] = []

    @dataclass
    class Result:
        id: str | None
        name: str
        description: str | None

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
        logger.debug(result)
        if not result:
            return self.Result(None, ocr_result, None)
        return self.Result(self._data[self._names.index(result.result)]["id"], ocr_result, self._data[self._names.index(result.result)]["description"])