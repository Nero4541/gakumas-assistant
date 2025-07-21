import multiprocessing

import uvicorn
import sys
import ctypes
import webbrowser

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


if __name__ == "__main__":
    host, port = "localhost", 8000
    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        sys.exit()
    # webbrowser.open(f"http://{host}:{port}")
    uvicorn.run("src.main:app", host=host, port=port, log_level="warning", reload=False)