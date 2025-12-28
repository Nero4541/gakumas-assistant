import sys


def is_compiled():
    # Nuitka 检测（模块和函数都有 __compiled__）
    if "__compiled__" in globals():
        return True

    # PyInstaller / cx_Freeze 等工具检测
    if getattr(sys, "frozen", False):
        return True
    return False