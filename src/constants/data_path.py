import os


class DataPath:
    DATABASE = os.path.join(os.getcwd(), 'data/db.sqlite3')
    class GakumasuDiffData:
        _base = os.path.join(os.getcwd(), "assets/gakumasu-diff")
        ITEM = os.path.join(_base, "Item.yaml")

    class GakumasTranslationData:
        _base = os.path.join(os.getcwd(), "assets/GakumasTranslationData/local-files/masterTrans")
        ITEM = os.path.join(_base, "Item.json")