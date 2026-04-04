from __future__ import annotations

from pathlib import Path

import rapidocr as rapidocr_package
from rapidocr import EngineType, LangDet, LangRec, ModelType, OCRVersion, RapidOCR

from src.core.inference.ocr_backends.base import BaseOCRBackend, OCRBackendResult
from src.utils.dml_manager import DMLManager
from src.utils.logger import logger
from src.utils.runtime_paths import resolve_runtime_path


class RapidOCRBackend(BaseOCRBackend):
    name = "rapidocr"
    requires_dml_lock = True

    @staticmethod
    def _resolve_resource_path(relative_path: str) -> str | None:
        relative = Path(relative_path)
        candidates = [
            resolve_runtime_path("rapidocr") / relative,
            Path(rapidocr_package.__file__).resolve().parent / relative,
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        logger.info(
            "RapidOCR resource {} not found locally, fallback to RapidOCR default model resolution. Looked in: {}",
            relative_path,
            ", ".join(str(path) for path in candidates),
        )
        return None

    @staticmethod
    def _create_accelerated_session(model_path: str):
        try:
            return DMLManager.create_dml_session(model_path)
        except Exception as exc:
            logger.warning(
                "Failed to create accelerated OCR session for {}, fallback to RapidOCR default session: {}",
                model_path,
                exc,
            )
            return None

    @staticmethod
    def _attach_accelerated_session(engine, component_name: str, session) -> None:
        if session is None:
            return
        component = getattr(engine, component_name, None)
        if component is None or not hasattr(component, "session"):
            logger.warning(
                "RapidOCR component {} is unavailable, skip attaching accelerated session.",
                component_name,
            )
            return
        component.session.session = session
        logger.info(
            "Attached accelerated OCR session to {} with providers: {}",
            component_name,
            session.get_providers(),
        )

    def __init__(self):
        det_model_path = self._resolve_resource_path("models/ch_PP-OCRv5_mobile_det.onnx")
        cls_model_path = self._resolve_resource_path("models/ch_ppocr_mobile_v2.0_cls_infer.onnx")
        rec_model_path = self._resolve_resource_path("models/japan_PP-OCRv4_rec_infer.onnx")
        det_session = self._create_accelerated_session(det_model_path) if det_model_path else None
        cls_session = self._create_accelerated_session(cls_model_path) if cls_model_path else None
        rec_session = self._create_accelerated_session(rec_model_path) if rec_model_path else None

        params = {
            "EngineConfig.onnxruntime.use_dml": "DmlExecutionProvider" in DMLManager.get_session_providers(),
            "Global.use_cls": False,
            "Global.min_height": 10,
            "Det.engine_type": EngineType.ONNXRUNTIME,
            "Det.lang_type": LangDet.CH,
            "Det.model_type": ModelType.MOBILE,
            "Det.ocr_version": OCRVersion.PPOCRV5,
            "Rec.engine_type": EngineType.ONNXRUNTIME,
            "Rec.lang_type": LangRec.JAPAN,
            "Rec.model_type": ModelType.MOBILE,
        }
        if det_model_path is not None:
            params["Det.model_path"] = det_model_path
        if cls_model_path is not None:
            params["Cls.model_path"] = cls_model_path
        if rec_model_path is not None:
            params["Rec.model_path"] = rec_model_path

        self._ocr = RapidOCR(params=params)
        self._attach_accelerated_session(self._ocr, "text_det", det_session)
        self._attach_accelerated_session(self._ocr, "text_cls", cls_session)
        self._attach_accelerated_session(self._ocr, "text_rec", rec_session)
        logger.info("Initialized OCR backend rapidocr")

    def infer(self, img, use_cls: bool = False) -> OCRBackendResult:
        raw_result = self._ocr(img, use_cls=use_cls)
        if raw_result is None or getattr(raw_result, "boxes", None) is None:
            return OCRBackendResult()
        return OCRBackendResult(
            boxes=list(raw_result.boxes),
            txts=list(raw_result.txts),
            scores=list(raw_result.scores),
        )
