from src.core.inference.ocr_backends.base import BaseOCRBackend, OCRBackendResult
from src.core.inference.ocr_backends.factory import (
    create_ocr_backend,
    get_requested_ocr_backend,
    normalize_ocr_backend_name,
    resolve_ocr_backend_candidates,
)
from src.core.inference.ocr_backends.rapidocr_backend import RapidOCRBackend
from src.core.inference.ocr_backends.vision_backend import (
    VisionOCRBackend,
    get_vision_unavailability_reason,
    vision_backend_is_available,
)

__all__ = [
    "BaseOCRBackend",
    "OCRBackendResult",
    "RapidOCRBackend",
    "VisionOCRBackend",
    "create_ocr_backend",
    "get_requested_ocr_backend",
    "get_vision_unavailability_reason",
    "normalize_ocr_backend_name",
    "resolve_ocr_backend_candidates",
    "vision_backend_is_available",
]
