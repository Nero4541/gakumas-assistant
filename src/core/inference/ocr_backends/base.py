from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np


@dataclass
class OCRBackendResult:
    boxes: list[np.ndarray] = field(default_factory=list)
    txts: list[str] = field(default_factory=list)
    scores: list[float | None] = field(default_factory=list)


class BaseOCRBackend(ABC):
    name = "unknown"
    requires_dml_lock = False

    @abstractmethod
    def infer(self, img: np.ndarray, use_cls: bool = False) -> OCRBackendResult:
        raise NotImplementedError
