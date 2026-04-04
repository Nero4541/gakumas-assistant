from __future__ import annotations

from contextlib import nullcontext
import platform

import cv2
import numpy as np

from src.core.inference.ocr_backends.base import BaseOCRBackend, OCRBackendResult
from src.utils.logger import logger

_VISION_IMPORT_ERROR = None
_objc = None
NSData = None
VNImageRequestHandler = None
VNRecognizeTextRequest = None
VNRequestTextRecognitionLevelAccurate = None

if platform.system() == "Darwin":
    try:
        import objc as _objc  # type: ignore[import-not-found]
        from Foundation import NSData  # type: ignore[import-not-found]
        from Vision import (  # type: ignore[import-not-found]
            VNImageRequestHandler,
            VNRecognizeTextRequest,
            VNRequestTextRecognitionLevelAccurate,
        )
    except Exception as exc:  # pragma: no cover - exercised through availability helpers
        _VISION_IMPORT_ERROR = exc


def vision_backend_is_available() -> bool:
    return platform.system() == "Darwin" and _VISION_IMPORT_ERROR is None


def get_vision_unavailability_reason() -> str:
    if platform.system() != "Darwin":
        return "Vision OCR backend is only available on macOS."
    if _VISION_IMPORT_ERROR is not None:
        return (
            f"Vision OCR backend is unavailable: {_VISION_IMPORT_ERROR}. "
            "Install or refresh dependencies in the active environment with "
            "`pip install -r requirements.txt`."
        )
    return ""


class VisionOCRBackend(BaseOCRBackend):
    name = "vision"
    requires_dml_lock = False

    def __init__(self):
        if not vision_backend_is_available():
            raise RuntimeError(get_vision_unavailability_reason())
        self._recognition_languages = ["ja-JP", "zh-Hans", "en-US"]
        logger.info("Initialized OCR backend vision")

    @staticmethod
    def _autorelease_pool():
        if _objc is not None and hasattr(_objc, "autorelease_pool"):
            return _objc.autorelease_pool()
        return nullcontext()

    @staticmethod
    def _first_candidate(candidates):
        if candidates is None:
            return None
        if hasattr(candidates, "firstObject"):
            return candidates.firstObject()
        if len(candidates) <= 0:
            return None
        return candidates[0]

    @staticmethod
    def _perform_requests(handler, requests):
        result = handler.performRequests_error_(requests, None)
        if isinstance(result, tuple):
            success = bool(result[0])
            error = result[1] if len(result) > 1 else None
            return success, error
        return bool(result), None

    @staticmethod
    def _normalized_box_to_quad(box, width: int, height: int) -> np.ndarray | None:
        rect_x = float(box.origin.x) * width
        rect_y = float(1.0 - box.origin.y - box.size.height) * height
        rect_w = float(box.size.width) * width
        rect_h = float(box.size.height) * height

        x = max(0.0, min(rect_x, float(width)))
        y = max(0.0, min(rect_y, float(height)))
        w = max(0.0, min(rect_w, float(width) - x))
        h = max(0.0, min(rect_h, float(height) - y))
        if w <= 0 or h <= 0:
            return None
        return np.array(
            [
                [x, y],
                [x + w, y],
                [x + w, y + h],
                [x, y + h],
            ],
            dtype=np.float32,
        )

    def _create_request(self):
        request = VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(VNRequestTextRecognitionLevelAccurate)
        if hasattr(request, "setUsesLanguageCorrection_"):
            request.setUsesLanguageCorrection_(False)
        if hasattr(request, "setRecognitionLanguages_"):
            request.setRecognitionLanguages_(self._recognition_languages)
        if hasattr(request, "setAutomaticallyDetectsLanguage_"):
            request.setAutomaticallyDetectsLanguage_(False)
        return request

    def infer(self, img, use_cls: bool = False) -> OCRBackendResult:
        del use_cls
        if img is None or img.size == 0:
            return OCRBackendResult()

        height, width = img.shape[:2]
        with self._autorelease_pool():
            success, encoded = cv2.imencode(".png", img)
            if not success:
                raise RuntimeError("Failed to encode image for Vision OCR.")

            image_bytes = encoded.tobytes()
            data = NSData.dataWithBytes_length_(image_bytes, len(image_bytes))
            request = self._create_request()
            handler = VNImageRequestHandler.alloc().initWithData_options_(data, None)
            request_success, request_error = self._perform_requests(handler, [request])
            if not request_success:
                raise RuntimeError(
                    f"Vision OCR request failed: {request_error or 'unknown error'}"
                )

            observations = request.results() or []
            items = []
            for observation in observations:
                candidates = observation.topCandidates_(1)
                candidate = self._first_candidate(candidates)
                if candidate is None:
                    continue
                text = str(candidate.string()).strip()
                if not text:
                    continue
                quad = self._normalized_box_to_quad(observation.boundingBox(), width, height)
                if quad is None:
                    continue
                confidence = float(candidate.confidence()) if hasattr(candidate, "confidence") else None
                x = float(quad[0][0])
                y = float(quad[0][1])
                items.append((y, x, quad, text, confidence))

        items.sort(key=lambda item: (item[0], item[1]))
        return OCRBackendResult(
            boxes=[item[2] for item in items],
            txts=[item[3] for item in items],
            scores=[item[4] for item in items],
        )
