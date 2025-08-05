import os

from peewee import SqliteDatabase, Model

db = SqliteDatabase(os.path.join(os.getcwd(), 'data', 'db.sqlite3'))


class BaseModel(Model):
    class Meta:
        database = db
