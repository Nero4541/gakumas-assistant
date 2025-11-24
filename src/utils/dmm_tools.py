# https://github.com/a4nqi3n/Gakumas_Launcher
import os
import re
from dataclasses import dataclass

from src.constants.path.data_path import DataPath


@dataclass
class DMM_UserInfo:
    exe_path: str
    viewer_id: int
    open_id: str
    pf_token: str


def extract_gakumas_launch_parameters():
    """从 DMMGamePlayer 日志中提取 Gakumas 启动信息"""
    log_path = DataPath.DMMPlayerDLL_Log

    if not os.path.exists(log_path):
        raise FileNotFoundError(f"Log file not found: {log_path}")

    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    target_line = next((line for line in reversed(lines) if "Execute of:: gakumas exe" in line), None)
    if not target_line:
        raise ValueError("No gakumas.exe launch record found in log.")

    regex = re.compile(
        r"exe:\s*(?P<exe_path>.*?gakumas\.exe).*?"
        r"/viewer_id=(?P<viewer_id>[^\s]+).*?"
        r"/open_id=(?P<open_id>[^\s]+).*?"
        r"/pf_access_token=(?P<pf_token>[^\s]+)"
    )

    match = regex.search(target_line)
    if not match:
        raise ValueError("Failed to parse launch information from log line.")

    return DMM_UserInfo(**dict(match.groupdict()))

if __name__ == '__main__':
    print(extract_gakumas_launch_parameters())