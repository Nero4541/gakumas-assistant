from __future__ import annotations

import os
import platform

from src.constants.ocr.backend import OCR_BACKEND_VALUES, OCRBackendType
from src.core.inference.ocr_backends.base import BaseOCRBackend
from src.core.inference.ocr_backends.rapidocr_backend import RapidOCRBackend
from src.core.inference.ocr_backends.vision_backend import VisionOCRBackend
from src.utils.logger import logger


def normalize_ocr_backend_name(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in OCR_BACKEND_VALUES:
        return normalized
    return OCRBackendType.AUTO


def _load_configured_ocr_backend() -> str:
    from src.core.services.config_service import ConfigService

    return str(ConfigService().base.ocr_backend)


def get_requested_ocr_backend() -> str:
    if env_backend := os.getenv("GAKUMAS_OCR_BACKEND"):
        normalized = normalize_ocr_backend_name(env_backend)
        if normalized != env_backend.strip().lower():
            logger.warning(
                "Invalid GAKUMAS_OCR_BACKEND value {}, fallback to {}.",
                env_backend,
                normalized,
            )
        return normalized
    return normalize_ocr_backend_name(_load_configured_ocr_backend())


def resolve_ocr_backend_candidates(
    requested_backend: str,
    current_platform: str | None = None,
) -> list[str]:
    current_platform = current_platform or platform.system()
    normalized = normalize_ocr_backend_name(requested_backend)
    if normalized == OCRBackendType.AUTO:
        if current_platform == "Darwin":
            return [OCRBackendType.VISION, OCRBackendType.RAPIDOCR]
        return [OCRBackendType.RAPIDOCR]
    if normalized == OCRBackendType.VISION:
        return [OCRBackendType.VISION, OCRBackendType.RAPIDOCR]
    return [OCRBackendType.RAPIDOCR]


def _build_backend(backend_name: str) -> BaseOCRBackend:
    if backend_name == OCRBackendType.VISION:
        return VisionOCRBackend()
    if backend_name == OCRBackendType.RAPIDOCR:
        return RapidOCRBackend()
    raise ValueError(f"Unknown OCR backend: {backend_name}")


def create_ocr_backend(requested_backend: str | None = None) -> BaseOCRBackend:
    requested = normalize_ocr_backend_name(requested_backend or get_requested_ocr_backend())
    candidates = resolve_ocr_backend_candidates(requested)
    errors = []
    primary_candidate = candidates[0] if candidates else requested
    for candidate in candidates:
        try:
            backend = _build_backend(candidate)
            if requested == OCRBackendType.AUTO:
                if candidate == primary_candidate:
                    logger.info("Using OCR backend {} (auto)", candidate)
                else:
                    logger.warning(
                        "Primary auto OCR backend {} is unavailable, fallback to {}.",
                        primary_candidate,
                        candidate,
                    )
            elif candidate != requested:
                logger.warning(
                    "OCR backend {} is unavailable, fallback to {}.",
                    requested,
                    candidate,
                )
            else:
                logger.info("Using OCR backend {}", candidate)
            return backend
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")
            logger.warning("Failed to initialize OCR backend {}: {}", candidate, exc)
    raise RuntimeError(
        "Failed to initialize any OCR backend. Attempted: " + " | ".join(errors)
    )
