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
    "rapidocr/config.yaml"
]

def ignore_unnecessary(dir, files):
    ignore_list = ['.git', '.gitignore', '__pycache__', '.DS_Store']
    return [f for f in files if f in ignore_list]

def build_webui():
    print("开始构建前端...")
    npm_cmd = "npm.cmd" if platform.system() == "Windows" else "npm"
    os.chdir("web-ui")
    subprocess.run([npm_cmd, "install"], shell=True, check=True)
    subprocess.run([npm_cmd, "run", "build"], shell=True, check=True)
    os.chdir("..")

def build_project():
    build_webui()
    print("开始打包APP")
    nuitka_cmd = [
        "--mingw64",
        "--standalone",
        "--show-memory",
        "--show-progress",
        "--nofollow-import-to=tkinter",
        "--nofollow-import-to=pytouch",
        "--enable-plugin=no-qt",
        # "--include-data-dir=assets=assets",
        # "--include-data-dir=bin=bin",
        # "--include-data-dir=model=model",
        # "--include-data-dir=dist=dist",
        # '--company-name=Pigeon Server Team',
        # f'--product-name={PROJECT_NAME}',
        f'--output-filename={PROJECT_NAME}.exe',
        f'--output-dir={NUITKA_OUTPUT_DIR}',
        f'--linux-icon={LOGO}',
        f'--windows-icon-from-ico={LOGO}',
        "--windows-disable-console",
        "app.py"
    ]
    subprocess.run([sys.executable, "-m", "nuitka"] + nuitka_cmd, shell=True, check=True)
    print("正在复制资源...")
    app_dist_path = os.path.join(NUITKA_OUTPUT_DIR, "app.dist")
    for key, value in COPY_ASSETS.items():
        print(f"{key}->{app_dist_path}/{value}")
        if os.path.isdir(key):
            shutil.copytree(key, os.path.join(app_dist_path, value), dirs_exist_ok=True, ignore=ignore_unnecessary)
        else:
            shutil.copy(key, os.path.join(app_dist_path, value))
    print("正在复制软件包附件...")
    for item in COPY_SITE_PACKAGES_FILES:
        target = os.path.join(app_dist_path, item)
        print(f"{os.path.join(sysconfig.get_paths()['purelib'], item)} -> {target}")
        if os.path.isdir(os.path.join(sysconfig.get_paths()['purelib'], item)):
            shutil.copytree(
                os.path.join(sysconfig.get_paths()["purelib"], item),
                target,
                dirs_exist_ok=True,
                ignore=ignore_unnecessary
            )
        else:
            shutil.copy(
                os.path.join(sysconfig.get_paths()["purelib"], item),
                target
            )

    print("✅ 打包完成！")

if __name__ == "__main__":
    build_project()
