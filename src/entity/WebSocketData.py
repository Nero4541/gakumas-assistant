import json
from dataclasses import dataclass

from src.utils.json_encoder import ComplexEncoder


@dataclass
class WebSocketData:
    message: str
    data: bytes
    def __init__(self, message:str | dict | None = None, data: bytes | None = None):
        if isinstance(message, dict):
            self.message = json.dumps(message, cls=ComplexEncoder)
        else:
            self.message = message
        self.message = message
        self.data = data