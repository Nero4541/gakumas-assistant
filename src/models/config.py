from datetime import datetime

from peewee import AutoField, CharField, BooleanField, DateTimeField

from src.models.base import BaseModel


class Config(BaseModel):
    id = AutoField(primary_key=True)
    key = CharField(unique=True)
    value = CharField(unique=True, default="")
    verify = CharField(unique=False, default=None)
    use_verify = BooleanField(unique=True, default=False)
    last_modified_time = DateTimeField(unique=False, default=datetime.now)