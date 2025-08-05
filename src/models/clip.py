from peewee import *
import pickle
import hashlib
import numpy as np
from uuid import uuid4

from src.models.base import BaseModel


class CLIPPayload(BaseModel):
    id = AutoField()
    type = CharField()
    hash = CharField(unique=True)
    data = BlobField()
    text = CharField()

    @classmethod
    def _hash(cls, b: bytes) -> str:
        return hashlib.sha256(b).hexdigest()

    @classmethod
    def save_payload(cls, payload_obj):
        b = pickle.dumps(payload_obj)
        h = cls._hash(b)
        obj, _ = cls.get_or_create(hash=h, defaults={
            'type': type(payload_obj).__name__,
            'data': b,
            'text': str(payload_obj)
        })
        return obj

    def load_payload(self):
        return pickle.loads(bytes(self.data))


class CLIPMemory(BaseModel):
    uuid = UUIDField(default=uuid4, unique=True, primary_key=True)
    type = CharField()
    payload = ForeignKeyField(CLIPPayload, backref="clip_memory_items", on_delete="CASCADE")
    features = BlobField()

    @classmethod
    def save_vector(cls, features: np.ndarray, payload_obj) -> "CLIPMemory":
        payload = CLIPPayload.save_payload(payload_obj)
        return cls.create(
            features=features.astype(np.float32).tobytes(),
            payload=payload
        )

    def load_features(self, dtype=np.float32) -> np.ndarray:
        return np.frombuffer(self.features, dtype=dtype)
