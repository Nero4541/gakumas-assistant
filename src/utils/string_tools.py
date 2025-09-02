import re

from dataclasses import dataclass
from typing import List

import unicodedata
from rapidfuzz import fuzz

# from src.utils.performance_tools import timeit


@dataclass
class MatchConfig:
    # 匹配对象
    # match: List[str] | str
    # 是否使用正则表达式匹配
    use_regex: bool = False
    # 是否使用模糊匹配
    use_fuzz: bool = True
    # fuzz模糊匹配阈值
    fuzz_threshold: float = 80

@dataclass
class MatchResult:
    config: MatchConfig
    status: bool
    result: str | None
    threshold: float

    def __bool__(self) -> bool:
        return bool(self.status)

# @timeit
def string_match(source: List[str] | str, match: List[str] | str, config: MatchConfig = None) -> MatchResult:
    match_obj = match if isinstance(match, list) else [match]
    config = config if config is not None else MatchConfig()
    if isinstance(source, str):
        if config.use_regex:
            for candidate in match_obj:
                if re.search(source, candidate):
                    return MatchResult(status=True, result=candidate, threshold=100, config=config)  # 正则匹配成功，返回结果
            return MatchResult(status=False, result=None, threshold=100, config=config)
        if config.use_fuzz:
            best_match = None
            best_score = 0
            # 使用 rapidfuzz 对每个匹配对象进行模糊匹配
            for candidate in match_obj:
                score = fuzz.ratio(source, candidate)
                if score > best_score:
                    best_score = score
                    best_match = candidate
            # 如果最佳匹配得分超过阈值，则返回
            if best_score >= config.fuzz_threshold:
                return MatchResult(status=True, result=best_match, threshold=best_score, config=config)
        for match in match_obj:
            if match in source:
                return MatchResult(status=True, result=match, threshold=100, config=config)
        return MatchResult(status=False, result=None, threshold=0, config=config)
    if isinstance(source, list):
        best_match = None
        best_score = 0
        for text in source:
            # 对列表中的每个字符串进行匹配
            if config.use_regex:
                for candidate in match_obj:
                    if re.search(candidate, text):  # 正则匹配
                        return MatchResult(status=True, result=candidate, threshold=100, config=config)
            if config.use_fuzz:
                # 使用 fuzzy 模糊匹配
                for candidate in match_obj:
                    score = fuzz.ratio(text, candidate)
                    if score > best_score:
                        best_score = score
                        best_match = candidate
                if best_score >= config.fuzz_threshold:
                    return MatchResult(status=True, result=best_match, threshold=best_score, config=config)
            # 如果启用了简单子串匹配
            for match in match_obj:
                if match in text:
                    return MatchResult(status=True, result=match, threshold=100, config=config)
    return MatchResult(status=False, result=None, threshold=0, config=config)

def fullwidth_to_halfwidth(text):
    """从全角字符转换到到半角字符"""
    halfwidth_text = ''.join(
        [unicodedata.normalize('NFKC', char) for char in text]
    )
    return halfwidth_text