import platform
import subprocess
import shutil
import os
import sys
import sysconfig
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

WEBUI_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "web-ui")
PROJECT_NAME = "Gakumas Assistant"
NUITKA_OUTPUT_DIR = "out"
LOGO = "./assets/images/gakumas_logo.png"
COPY_ASSETS = {
    "assets": "assets",
    "bin": "bin",
    "model": "model",
    "dist": "dist"
}
COPY_SITE_PACKAGES_FILES = [
    "rapidocr/models",
    "rapidocr/default_models.yaml",
    "rapidocr/config.yaml",
    "LICENSE",
    "README.md",
]

def ignore_unnecessary(dir, files):
    ignore_list = ['.git', '.gitignore', '__pycache__', '.DS_Store']
    return [f for f in files if f in ignore_list]

def update_game_database():
    subprocess.run(["git", "submodule", "update"], shell=True, check=True)

def build_webui():
    npm_cmd = "npm.cmd" if platform.system() == "Windows" else "npm"
    os.chdir("web-ui")
    subprocess.run([npm_cmd, "install", "--force"], shell=True, check=True)
    subprocess.run([npm_cmd, "run", "build"], shell=True, check=True)
    os.chdir("..")

def build_project():
    if os.getenv("GITHUB_ACTIONS"):
        update_game_database()
    build_webui()
    nuitka_cmd = [
        "--standalone",
        "--nofollow-import-to=tkinter",
        "--nofollow-import-to=pytouch",
        "--nofollow-import-to=touch",
        "--enable-plugin=no-qt",
        f'--output-filename={PROJECT_NAME}.exe',
        f'--output-dir={NUITKA_OUTPUT_DIR}',
        f'--linux-icon={LOGO}',
        f'--windows-icon-from-ico={LOGO}',
        "--windows-console-mode=attach",
        "--no-deployment-flag=self-execution",
    ]

    if not os.getenv("GITHUB_ACTIONS"):
        nuitka_cmd.append("--show-progress")
    else:
        nuitka_cmd.append("--low-memory")

    for item in COPY_SITE_PACKAGES_FILES:
        target = os.path.join(sysconfig.get_paths()['purelib'], item)
        if os.path.isdir(target):
            nuitka_cmd += [f"--include-data-dir={target}={item}"]
        elif os.path.isfile(target):
            nuitka_cmd += [f"--include-data-files={target}={item}"]

    subprocess.run([sys.executable, "-m", "nuitka"] + nuitka_cmd + ["app.py"], shell=True, check=True)
    app_dist_path = os.path.join(NUITKA_OUTPUT_DIR, "app.dist")
    for key, value in COPY_ASSETS.items():
        print(f"[copy]{key}->{app_dist_path}/{value}")
        if os.path.isdir(key):
            shutil.copytree(key, os.path.join(app_dist_path, value), dirs_exist_ok=True, ignore=ignore_unnecessary)
        else:
            shutil.copy(key, os.path.join(app_dist_path, value))

if __name__ == "__main__":
    build_project()
