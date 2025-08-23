import os

from peewee import SqliteDatabase, Model

from src.constants.data_path import DataPath

db = SqliteDatabase(DataPath.DATABASE)

class BaseModel(Model):
    class Meta:
        database = db
