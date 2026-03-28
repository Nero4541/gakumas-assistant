import os
import platform
import tempfile
import threading
from pathlib import Path

import onnxruntime as ort

from src.utils.logger import logger
from src.utils.runtime_paths import resolve_cache_path

class DMLManager:
    _lock = threading.Lock()
    _preferred_execution_providers = (
        "DmlExecutionProvider",
        "CoreMLExecutionProvider",
        "CPUExecutionProvider",
    )

    @classmethod
    def run(cls, session: ort.InferenceSession, feeds: dict):
        with cls._lock:
            return session.run(None, feeds)

    @classmethod
    def get_lock(cls):
        with cls._lock:
            return cls._lock

    @classmethod
    def get_session_providers(cls) -> list[str]:
        available_providers = set(ort.get_available_providers())
        providers = [
            provider
            for provider in cls._preferred_execution_providers
            if provider in available_providers
        ]
        if "CPUExecutionProvider" not in providers:
            providers.append("CPUExecutionProvider")
        return providers

    @staticmethod
    def _get_cache_root() -> Path:
        candidates = []
        if custom_cache_dir := os.environ.get("GAKUMAS_CACHE_DIR"):
            candidates.append(Path(custom_cache_dir))

        candidates.append(resolve_cache_path("onnxruntime"))
        candidates.append(Path(tempfile.gettempdir()) / "gakumas-assistant")

        for base_dir in candidates:
            try:
                base_dir.mkdir(parents=True, exist_ok=True)
                return base_dir
            except OSError:
                continue

        raise RuntimeError("No writable cache directory available for ONNX Runtime.")

    @classmethod
    def _build_provider_config(cls):
        providers = []
        available_providers = cls.get_session_providers()

        if "DmlExecutionProvider" in available_providers:
            providers.append("DmlExecutionProvider")

        if "CoreMLExecutionProvider" in available_providers:
            cache_root = cls._get_cache_root()
            tmp_dir = cache_root / "tmp"
            cache_dir = cache_root / "coreml-cache"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            cache_dir.mkdir(parents=True, exist_ok=True)

            # CoreML compilation can fail under the default macOS temp directory in sandboxed
            # or packaged environments, so pin it to an app-owned writable cache directory.
            os.environ["TMPDIR"] = str(tmp_dir)

            mac_version = platform.mac_ver()[0]
            try:
                major_version = int(mac_version.split(".", 1)[0]) if mac_version else 0
            except ValueError:
                major_version = 0
            model_format = "MLProgram" if major_version >= 12 else "NeuralNetwork"

            providers.append(
                (
                    "CoreMLExecutionProvider",
                    {
                        "ModelFormat": model_format,
                        "MLComputeUnits": "ALL",
                        "RequireStaticInputShapes": "0",
                        "EnableOnSubgraphs": "0",
                        "ModelCacheDirectory": str(cache_dir),
                    },
                )
            )

        if "CPUExecutionProvider" in available_providers:
            providers.append("CPUExecutionProvider")

        return providers

    @staticmethod
    def create_dml_session(model_path: str) -> ort.InferenceSession:
        so = ort.SessionOptions()
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        so.intra_op_num_threads = 1
        so.inter_op_num_threads = 1
        providers = DMLManager._build_provider_config()
        logger.debug(f"Create ONNX session with providers: {providers}")
        try:
            return ort.InferenceSession(
                model_path,
                sess_options=so,
                providers=providers,
            )
        except Exception as exc:
            fallback_providers = ["CPUExecutionProvider"]
            if providers == fallback_providers:
                raise
            logger.warning(
                "Create accelerated ONNX session failed for {}, fallback to CPUExecutionProvider: {}",
                model_path,
                exc,
            )
            return ort.InferenceSession(
                model_path,
                sess_options=so,
                providers=fallback_providers,
            )
