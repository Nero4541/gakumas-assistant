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
    # 是否启用子串匹配（fuzz 失败后的回退）
    use_contains: bool = True
    # 是否在比较前进行全角→半角归一化
    normalize: bool = False

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
    """
    匹配字符串
    :param source: 源
    :param match: 匹配列表
    :param config: 匹配配置
    :return:
    """
    match_obj = match if isinstance(match, list) else [match]
    config = config if config is not None else MatchConfig()

    # 归一化预处理
    if config.normalize:
        _norm = fullwidth_to_halfwidth
        # 保留 原始值→归一化值 的反向映射，以便返回原始候选
        _norm_map = {_norm(c): c for c in match_obj}
        match_obj_cmp = list(_norm_map.keys())
    else:
        _norm = lambda x: x
        _norm_map = None
        match_obj_cmp = match_obj

    def _unwrap(candidate: str) -> str:
        """把归一化后的候选还原成原始值"""
        if _norm_map is not None:
            return _norm_map.get(candidate, candidate)
        return candidate

    if isinstance(source, str):
        src_cmp = _norm(source)
        if config.use_regex:
            for candidate in match_obj_cmp:
                if re.search(src_cmp, candidate):
                    return MatchResult(status=True, result=_unwrap(candidate), threshold=100, config=config)
            return MatchResult(status=False, result=None, threshold=100, config=config)
        if config.use_fuzz:
            best_match = None
            best_score = 0
            for candidate in match_obj_cmp:
                score = fuzz.ratio(src_cmp, candidate)
                if score > best_score:
                    best_score = score
                    best_match = candidate
            if best_score >= config.fuzz_threshold:
                return MatchResult(status=True, result=_unwrap(best_match), threshold=best_score, config=config)
        if config.use_contains:
            for m in match_obj_cmp:
                if m in src_cmp:
                    return MatchResult(status=True, result=_unwrap(m), threshold=100, config=config)
        return MatchResult(status=False, result=None, threshold=0, config=config)
    if isinstance(source, list):
        best_match = None
        best_score = 0
        for text in source:
            text_cmp = _norm(text)
            if config.use_regex:
                for candidate in match_obj_cmp:
                    if re.search(candidate, text_cmp):
                        return MatchResult(status=True, result=_unwrap(candidate), threshold=100, config=config)
            if config.use_fuzz:
                for candidate in match_obj_cmp:
                    score = fuzz.ratio(text_cmp, candidate)
                    if score > best_score:
                        best_score = score
                        best_match = candidate
                if best_score >= config.fuzz_threshold:
                    return MatchResult(status=True, result=_unwrap(best_match), threshold=best_score, config=config)
            if config.use_contains:
                for m in match_obj_cmp:
                    if m in text_cmp:
                        return MatchResult(status=True, result=_unwrap(m), threshold=100, config=config)
    return MatchResult(status=False, result=None, threshold=0, config=config)

def fullwidth_to_halfwidth(text):
    """从全角字符转换到到半角字符"""
    halfwidth_text = ''.join(
        [unicodedata.normalize('NFKC', char) for char in text]
    )
    return halfwidth_text


# 日文OCR常见误识别字符映射表
# 形态相近的汉字会被识别成片假名或平假名，需要在使用前做标准化
_OCR_JP_CORRECTION_MAP: dict[str, str] = {
    # 长音符误识别
    '一': 'ー',  # CJK「一」→ カタカナ長音符「ー」(最常见)
    # 其他常见误识别（按需补充）
    '口': 'ロ',  # CJK「口」→「ロ」
    '力': 'カ',  # CJK「力」→「カ」
    '夕': 'タ',  # CJK「夕」→「タ」
    '工': 'エ',  # CJK「工」→「エ」
    '二': 'ニ',  # CJK「二」→「ニ」
    '八': 'ハ',  # CJK「八」→「ハ」
    '人': 'ヘ',  # CJK「人」→「ヘ」（形近）
    '十': '十',  # 保留原样（不混淆）
}


def normalize_ocr_jp(text: str) -> str:
    """修正日文OCR常见的形近字误识别，用于OCR结果后处理。"""
    return text.translate(str.maketrans(_OCR_JP_CORRECTION_MAP))