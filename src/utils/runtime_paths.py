import json
import os
from functools import lru_cache
from pathlib import Path

RUNTIME_METADATA_FILE_NAME = ".gakumas-runtime.json"
STORAGE_MODE_PORTABLE = "portable"
STORAGE_MODE_MERGED = "merged"


@lru_cache(maxsize=1)
def get_runtime_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_runtime_path(*parts) -> Path:
    return get_runtime_root().joinpath(*parts)


def resolve_runtime_str(*parts) -> str:
    return str(resolve_runtime_path(*parts))


def _normalize_storage_mode(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {STORAGE_MODE_PORTABLE, "local", "bundled"}:
        return STORAGE_MODE_PORTABLE
    if normalized in {STORAGE_MODE_MERGED, "managed", "user", "userdata"}:
        return STORAGE_MODE_MERGED
    return None


@lru_cache(maxsize=1)
def get_runtime_metadata_path() -> Path:
    return get_runtime_root() / RUNTIME_METADATA_FILE_NAME


@lru_cache(maxsize=1)
def get_runtime_metadata() -> dict:
    metadata_path = get_runtime_metadata_path()
    if not metadata_path.exists():
        return {}
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


@lru_cache(maxsize=1)
def get_storage_mode() -> str:
    env_mode = _normalize_storage_mode(os.environ.get("GAKUMAS_STORAGE_MODE"))
    if env_mode is not None:
        return env_mode

    metadata_mode = _normalize_storage_mode(get_runtime_metadata().get("storage_mode"))
    if metadata_mode is not None:
        return metadata_mode

    return STORAGE_MODE_PORTABLE


@lru_cache(maxsize=1)
def embedded_webview_enabled() -> bool:
    metadata = get_runtime_metadata()
    if "embedded_webview" not in metadata:
        return True
    return bool(metadata.get("embedded_webview"))


@lru_cache(maxsize=1)
def get_user_data_root() -> Path:
    return Path.home() / ".gakumas-assistant"


def resolve_user_data_path(*parts) -> Path:
    return get_user_data_root().joinpath(*parts)


@lru_cache(maxsize=1)
def get_storage_root() -> Path:
    if get_storage_mode() == STORAGE_MODE_PORTABLE:
        return get_runtime_root()
    return get_user_data_root()


def resolve_storage_path(*parts) -> Path:
    return get_storage_root().joinpath(*parts)


def resolve_storage_str(*parts) -> str:
    return str(resolve_storage_path(*parts))


@lru_cache(maxsize=1)
def get_cache_root() -> Path:
    return resolve_storage_path(".cache")


def resolve_cache_path(*parts) -> Path:
    return get_cache_root().joinpath(*parts)


def resolve_cache_str(*parts) -> str:
    return str(resolve_cache_path(*parts))


@lru_cache(maxsize=1)
def get_data_root() -> Path:
    return resolve_storage_path("data")


def resolve_data_path(*parts) -> Path:
    return get_data_root().joinpath(*parts)


def resolve_data_str(*parts) -> str:
    return str(resolve_data_path(*parts))


@lru_cache(maxsize=1)
def get_log_root() -> Path:
    return resolve_storage_path("logs")


def resolve_log_path(*parts) -> Path:
    return get_log_root().joinpath(*parts)


def resolve_log_str(*parts) -> str:
    return str(resolve_log_path(*parts))


@lru_cache(maxsize=1)
def get_managed_resource_root() -> Path:
    return resolve_storage_path("assets")


def resolve_managed_resource_path(*parts) -> Path:
    return get_managed_resource_root().joinpath(*parts)


def resolve_existing_resource_path(*parts) -> Path:
    managed_path = resolve_managed_resource_path(*parts)
    if managed_path.exists():
        return managed_path
    bundled_path = resolve_runtime_path(*parts)
    if bundled_path.exists():
        return bundled_path
    return managed_path


def resolve_existing_resource_str(*parts) -> str:
    return str(resolve_existing_resource_path(*parts))
