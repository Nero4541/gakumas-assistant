import os

from src.utils.runtime_paths import resolve_log_str


class DebugPath:
    __base = resolve_log_str("debug")
    __base_image = os.path.join(__base, "images")

    @classmethod
    def BasePath(cls):
        return cls.__base

    UnknownItem = os.path.join(__base_image, "UnknownItem")
    NotEnoughContests = os.path.join(__base_image, "NotEnoughContests")
    NoValidSkillCardInfo = os.path.join(__base_image, "NoValidSkillCardInfo")
