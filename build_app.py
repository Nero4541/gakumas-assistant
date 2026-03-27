import io
import json
import os
import platform
import shutil
import subprocess
import sys
import sysconfig
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent
WEBUI_DIR = PROJECT_ROOT / "web-ui"
PROJECT_NAME = "Gakumas Assistant"
TARGET_PLATFORM = platform.system()
NUITKA_OUTPUT_DIR = PROJECT_ROOT / "out"
APP_DIST_DIR = NUITKA_OUTPUT_DIR / "app.dist"
LOGO = PROJECT_ROOT / "assets" / "images" / "gakumas_logo.png"
NUITKA_REPORT_PATH = PROJECT_ROOT / ".cache" / "nuitka-compilation-report.xml"
WEBUI_DIST_DIR = PROJECT_ROOT / "dist"
WEBUI_BUILD_INPUTS = (
    WEBUI_DIR / "src",
    WEBUI_DIR / "public",
    WEBUI_DIR / "index.html",
    WEBUI_DIR / "package.json",
    WEBUI_DIR / "package-lock.json",
    WEBUI_DIR / "vite.config.mjs",
    WEBUI_DIR / "eslint.config.js",
)

GAKUMAS_DIFF_FILES = [
    "Item.yaml",
    "Character.yaml",
    "IdolCard.yaml",
    "SupportCard.yaml",
    "ProduceCard.yaml",
    "ProduceCardCustomize.yaml",
    "ProduceCardSearch.yaml",
    "ProduceCardStatusEnchant.yaml",
    "EffectGroup.yaml",
    "ProduceExamEffect.yaml",
    "ProduceExamTrigger.yaml",
    "ProduceCardGrowEffect.yaml",
    "ProduceExamStatusEnchant.yaml",
    "ProduceItem.yaml",
    "ProduceDrink.yaml",
    "ProduceSkill.yaml",
]
TRANSLATION_FILES = [Path(name).with_suffix(".json").name for name in GAKUMAS_DIFF_FILES]
MODEL_FILES = [
    "base_ui.onnx",
    "base_ui_meta.json",
    "producer.onnx",
    "producer_meta.json",
    "clip_visual.onnx",
]
RAPIDOCR_DATA_FILES = [
    "rapidocr/default_models.yaml",
    "rapidocr/config.yaml",
    "rapidocr/models/ch_PP-OCRv5_mobile_det.onnx",
    "rapidocr/models/ch_ppocr_mobile_v2.0_cls_infer.onnx",
    "rapidocr/models/japan_PP-OCRv4_rec_infer.onnx",
]
RESOURCE_REPOSITORIES = (
    {
        "name": "gakumasu-diff",
        "path": Path("assets") / "gakumasu-diff",
        "owner": "vertesan",
        "repo": "gakumasu-diff",
    },
    {
        "name": "GakumasTranslationData",
        "path": Path("assets") / "GakumasTranslationData",
        "owner": "chinosk6",
        "repo": "GakumasTranslationData",
    },
)


def ignore_unnecessary(_dir, files):
    ignore_list = {".git", ".gitignore", "__pycache__", ".DS_Store"}
    return [name for name in files if name in ignore_list]


def _get_output_filename() -> str:
    return f"{PROJECT_NAME}.exe" if TARGET_PLATFORM == "Windows" else PROJECT_NAME


def update_game_database():
    subprocess.run(
        ["git", "submodule", "update", "--init", "--recursive"],
        cwd=PROJECT_ROOT,
        check=True,
    )


def _iter_files(path: Path):
    if not path.exists():
        return
    if path.is_file():
        yield path
        return
    for file_path in path.rglob("*"):
        if file_path.is_file():
            yield file_path


def _get_latest_mtime(paths) -> float:
    latest_mtime = 0.0
    for path in paths:
        for file_path in _iter_files(path):
            latest_mtime = max(latest_mtime, file_path.stat().st_mtime)
    return latest_mtime


def _has_built_webui_dist() -> bool:
    index_html = WEBUI_DIST_DIR / "index.html"
    assets_dir = WEBUI_DIST_DIR / "assets"
    return index_html.exists() and assets_dir.exists()


def _webui_dist_is_fresh() -> bool:
    if not _has_built_webui_dist():
        return False
    latest_source_mtime = _get_latest_mtime(WEBUI_BUILD_INPUTS)
    latest_dist_mtime = _get_latest_mtime((WEBUI_DIST_DIR,))
    return latest_dist_mtime >= latest_source_mtime


def build_webui():
    if (
        not os.getenv("GITHUB_ACTIONS")
        and not os.getenv("FORCE_WEBUI_BUILD")
        and _webui_dist_is_fresh()
    ):
        print("Skipping web-ui build, existing dist is up to date")
        return

    npm_cmd = "npm.cmd" if platform.system() == "Windows" else "npm"
    npm_cache_dir = PROJECT_ROOT / ".cache" / "npm"
    node_modules_dir = WEBUI_DIR / "node_modules"
    vite_binary = node_modules_dir / ".bin" / ("vite.cmd" if platform.system() == "Windows" else "vite")
    npm_cache_dir.mkdir(parents=True, exist_ok=True)
    npm_env = os.environ.copy()
    npm_env.setdefault("NPM_CONFIG_CACHE", str(npm_cache_dir))
    install_args = ["ci"] if (WEBUI_DIR / "package-lock.json").exists() else ["install"]
    try:
        subprocess.run([npm_cmd, *install_args], cwd=WEBUI_DIR, check=True, env=npm_env)
    except subprocess.CalledProcessError:
        if install_args != ["ci"] or os.getenv("GITHUB_ACTIONS"):
            raise
        print("npm ci failed locally, retrying with npm install")
        try:
            subprocess.run([npm_cmd, "install"], cwd=WEBUI_DIR, check=True, env=npm_env)
        except subprocess.CalledProcessError:
            if not node_modules_dir.exists():
                raise
            print("npm install failed locally, reusing existing node_modules")
    if not vite_binary.exists():
        if not os.getenv("GITHUB_ACTIONS") and _has_built_webui_dist():
            print("Vite is unavailable locally, reusing existing dist")
            return
        raise RuntimeError("Vite is unavailable. Reinstall web-ui dependencies before building.")
    subprocess.run([npm_cmd, "run", "build"], cwd=WEBUI_DIR, check=True, env=npm_env)


def _add_rapidocr_data_files(nuitka_cmd: list[str]):
    purelib_dir = Path(sysconfig.get_paths()["purelib"])
    missing_files = []
    for relative_path in RAPIDOCR_DATA_FILES:
        source_path = purelib_dir / Path(relative_path)
        if not source_path.exists():
            missing_files.append(source_path)
    if missing_files:
        print("RapidOCR runtime files are missing, bootstrapping models before packaging")
        subprocess.run(
            [sys.executable, "-c", "from src.core.inference.ocr_engine import OCRLoader; OCRLoader()"],
            cwd=PROJECT_ROOT,
            check=True,
        )
    for relative_path in RAPIDOCR_DATA_FILES:
        source_path = purelib_dir / Path(relative_path)
        if not source_path.exists():
            raise FileNotFoundError(source_path)
        nuitka_cmd.append(f"--include-data-files={source_path}={relative_path}")


def _add_nuitka_dependency_pruning(nuitka_cmd: list[str]):
    # Uvicorn standard extras pull in optional reload/runtime helpers that this app does not use.
    nofollow_modules = [
        "tkinter",
        "pytouch",
        "touch",
        "matplotlib",
        "pandas",
        "onnxruntime.training",
        "onnxruntime.quantization",
        "onnxruntime.tools",
        "watchfiles",
        "watchgod",
        "uvloop",
        "dotenv",
    ]
    if TARGET_PLATFORM != "Windows":
        nofollow_modules.extend(
            [
                "webview",
                "Foundation",
                "AppKit",
                "Cocoa",
                "objc",
                "WebKit",
            ]
        )
    for module_name in nofollow_modules:
        nuitka_cmd.append(f"--nofollow-import-to={module_name}")

    # Use Nuitka's anti-bloat switches to stop scanning deployment-irrelevant module families.
    noinclude_modes = {
        "--noinclude-setuptools-mode": "nofollow",
        "--noinclude-pytest-mode": "nofollow",
        "--noinclude-unittest-mode": "nofollow",
        "--noinclude-pydoc-mode": "nofollow",
        "--noinclude-IPython-mode": "nofollow",
        "--noinclude-dask-mode": "nofollow",
        "--noinclude-numba-mode": "nofollow",
    }
    for option_name, mode in noinclude_modes.items():
        nuitka_cmd.append(f"{option_name}={mode}")

    noinclude_data_patterns = [
        "torch/include/**",
        "torch/bin/protoc*",
    ]
    for pattern in noinclude_data_patterns:
        nuitka_cmd.append(f"--noinclude-data-files={pattern}")


def _add_optional_nuitka_report(nuitka_cmd: list[str]):
    if not os.getenv("NUITKA_REPORT"):
        return
    NUITKA_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    nuitka_cmd.append(f"--report={NUITKA_REPORT_PATH}")
    nuitka_cmd.append("--report-diffable")


def _copy_file(source: Path, target: Path):
    if not source.exists():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _copy_directory(source: Path, target: Path):
    if not source.exists():
        raise FileNotFoundError(source)
    shutil.copytree(source, target, dirs_exist_ok=True, ignore=ignore_unnecessary)


def _copy_selected_files(source_dir: Path, target_dir: Path, file_names: list[str]):
    if not source_dir.exists():
        raise FileNotFoundError(source_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    for file_name in file_names:
        source_path = source_dir / file_name
        if source_path.exists():
            shutil.copy2(source_path, target_dir / file_name)


def _remove_existing_path(path: Path):
    if not path.exists():
        return
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    except OSError as exc:
        raise RuntimeError(
            f"Failed to clean previous build output: {path}. Close processes that may be using packaged files and retry."
        ) from exc


def _prepare_nuitka_output_paths():
    if os.getenv("NUITKA_CLEAN_BUILD"):
        _remove_existing_path(NUITKA_OUTPUT_DIR / "app.build")
    _remove_existing_path(APP_DIST_DIR)
    _remove_existing_path(NUITKA_OUTPUT_DIR / _get_output_filename())


def _get_nuitka_platform_options() -> list[str]:
    nuitka_cmd = [
        "--standalone",
        "--enable-plugin=no-qt",
        "--module-parameter=torch-disable-jit=no",
        f"--output-filename={_get_output_filename()}",
        f"--output-dir={NUITKA_OUTPUT_DIR}",
        "--no-deployment-flag=self-execution",
    ]

    if shutil.which("upx"):
        nuitka_cmd.append("--enable-plugin=upx")

    if TARGET_PLATFORM == "Windows":
        nuitka_cmd.append(f"--windows-icon-from-ico={LOGO}")
        nuitka_cmd.append("--windows-console-mode=attach")
    elif TARGET_PLATFORM == "Linux":
        nuitka_cmd.append(f"--linux-icon={LOGO}")

    return nuitka_cmd


def _resolve_git_dir(repo_path: Path) -> Path | None:
    git_entry = repo_path / ".git"
    if git_entry.is_dir():
        return git_entry
    if not git_entry.is_file():
        return None
    first_line = git_entry.read_text(encoding="utf-8").splitlines()[0].strip()
    if not first_line.startswith("gitdir:"):
        return None
    git_dir = Path(first_line.split(":", 1)[1].strip())
    if not git_dir.is_absolute():
        git_dir = (repo_path / git_dir).resolve()
    return git_dir


def _read_git_ref(git_dir: Path, ref_name: str) -> str:
    ref_path = git_dir.joinpath(*ref_name.split("/"))
    if ref_path.exists():
        return ref_path.read_text(encoding="utf-8").strip()
    packed_refs_path = git_dir / "packed-refs"
    if not packed_refs_path.exists():
        return ""
    with packed_refs_path.open("r", encoding="utf-8") as file_obj:
        for line in file_obj:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("^"):
                continue
            commit_sha, current_ref, *_ = line.split()
            if current_ref == ref_name:
                return commit_sha
    return ""


def _read_git_version(repo_path: Path) -> dict[str, str] | None:
    git_dir = _resolve_git_dir(repo_path)
    if git_dir is None:
        return None
    head_path = git_dir / "HEAD"
    if not head_path.exists():
        return None
    head_value = head_path.read_text(encoding="utf-8").strip()
    if not head_value:
        return None
    if head_value.startswith("ref: "):
        ref_name = head_value[5:].strip()
        commit_sha = _read_git_ref(git_dir, ref_name)
        if not commit_sha:
            return None
        return {
            "commit": commit_sha,
            "branch": ref_name.split("/")[-1],
            "source": "git",
        }
    return {
        "commit": head_value,
        "branch": "",
        "source": "git",
    }


def _load_repository_metadata(repository: dict) -> dict[str, str]:
    source_metadata_path = (
        PROJECT_ROOT
        / "data"
        / "resource_repository_versions"
        / f"{repository['name']}.json"
    )
    if source_metadata_path.exists():
        with source_metadata_path.open("r", encoding="utf-8") as file_obj:
            metadata = json.load(file_obj)
        metadata.setdefault("source", "metadata")
        return metadata

    git_version = _read_git_version(PROJECT_ROOT / repository["path"])
    if git_version is not None:
        return {
            "name": repository["name"],
            "path": str(repository["path"]).replace("\\", "/"),
            "owner": repository["owner"],
            "repo": repository["repo"],
            "commit": git_version.get("commit", ""),
            "branch": git_version.get("branch", ""),
            "source": git_version.get("source", "git"),
        }

    return {
        "name": repository["name"],
        "path": str(repository["path"]).replace("\\", "/"),
        "owner": repository["owner"],
        "repo": repository["repo"],
        "commit": "",
        "branch": "",
        "source": "build",
    }


def _write_resource_repository_versions(app_dist_path: Path):
    target_dir = app_dist_path / "data" / "resource_repository_versions"
    target_dir.mkdir(parents=True, exist_ok=True)
    updated_at = datetime.now().isoformat(timespec="seconds")
    for repository in RESOURCE_REPOSITORIES:
        metadata = _load_repository_metadata(repository)
        metadata.update(
            {
                "name": repository["name"],
                "path": str(repository["path"]).replace("\\", "/"),
                "owner": repository["owner"],
                "repo": repository["repo"],
                "updated_at": updated_at,
            }
        )
        target_path = target_dir / f"{repository['name']}.json"
        with target_path.open("w", encoding="utf-8") as file_obj:
            json.dump(metadata, file_obj, ensure_ascii=False, indent=2)


def _copy_runtime_files(app_dist_path: Path):
    _copy_file(
        PROJECT_ROOT / "assets" / "images" / "gakumas_logo.png",
        app_dist_path / "assets" / "images" / "gakumas_logo.png",
    )
    _copy_file(
        PROJECT_ROOT / "assets" / "NotoSerifCJKsc-Medium.otf",
        app_dist_path / "assets" / "NotoSerifCJKsc-Medium.otf",
    )
    _copy_selected_files(
        PROJECT_ROOT / "assets" / "gakumasu-diff",
        app_dist_path / "assets" / "gakumasu-diff",
        GAKUMAS_DIFF_FILES,
    )
    _copy_selected_files(
        PROJECT_ROOT / "assets" / "GakumasTranslationData" / "local-files" / "masterTrans",
        app_dist_path / "assets" / "GakumasTranslationData" / "local-files" / "masterTrans",
        TRANSLATION_FILES,
    )
    _copy_directory(PROJECT_ROOT / "bin", app_dist_path / "bin")
    _copy_directory(PROJECT_ROOT / "dist", app_dist_path / "dist")
    _copy_selected_files(PROJECT_ROOT / "model", app_dist_path / "model", MODEL_FILES)
    _write_resource_repository_versions(app_dist_path)
    if TARGET_PLATFORM != "Windows":
        webview_loader_path = app_dist_path / "bin" / "WebView2Loader.dll"
        if webview_loader_path.exists():
            webview_loader_path.unlink()


def build_project():
    if os.getenv("GITHUB_ACTIONS"):
        update_game_database()

    nuitka_cache_dir = Path(os.environ.setdefault("NUITKA_CACHE_DIR", str(PROJECT_ROOT / ".cache" / "nuitka")))
    nuitka_cache_dir.mkdir(parents=True, exist_ok=True)
    build_webui()
    _prepare_nuitka_output_paths()

    nuitka_cmd = _get_nuitka_platform_options()

    if os.getenv("GITHUB_ACTIONS") and TARGET_PLATFORM == "Windows":
        nuitka_cmd.append("--mingw64")
    if os.getenv("GITHUB_ACTIONS"):
        nuitka_cmd.append("--assume-yes-for-downloads")
    if os.getenv("NUITKA_SHOW_PROGRESS"):
        nuitka_cmd.append("--show-progress")

    _add_nuitka_dependency_pruning(nuitka_cmd)
    _add_optional_nuitka_report(nuitka_cmd)
    _add_rapidocr_data_files(nuitka_cmd)

    subprocess.run(
        [sys.executable, "-m", "nuitka", *nuitka_cmd, "app.py"],
        cwd=PROJECT_ROOT,
        check=True,
    )
    _copy_runtime_files(APP_DIST_DIR)


if __name__ == "__main__":
    build_project()
