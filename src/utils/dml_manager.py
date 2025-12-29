import threading
import onnxruntime as ort

class DMLManager:
    _lock = threading.Lock()

    @classmethod
    def run(cls, session: ort.InferenceSession, feeds: dict):
        with cls._lock:
            return session.run(None, feeds)

    @classmethod
    def get_lock(cls):
        with cls._lock:
            return cls._lock

    @staticmethod
    def create_dml_session(model_path: str) -> ort.InferenceSession:
        so = ort.SessionOptions()
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        so.intra_op_num_threads = 1
        so.inter_op_num_threads = 1

        return ort.InferenceSession(
            model_path,
            sess_options=so,
            providers=[
                "DmlExecutionProvider",
                "CPUExecutionProvider"
            ]
        )