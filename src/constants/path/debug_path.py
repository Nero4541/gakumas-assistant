import os


class DebugPath:
    __base = os.path.join(os.getcwd(), "logs", "debug")
    __base_image = os.path.join(__base, "images")

    @classmethod
    def BasePath(cls):
        return cls.__base

    UnknownItem = os.path.join(__base_image, "UnknownItem")
    NotEnoughContests = os.path.join(__base_image, "NotEnoughContests")