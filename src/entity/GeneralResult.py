from dataclasses import dataclass


@dataclass
class GeneralResult__Threshold:
    """
    用于阈值的通用返回体
    """
    status: bool
    threshold: float
    value: float

    def __bool__(self):
        return self.status