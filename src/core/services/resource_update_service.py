import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Event, Lock, Thread
from typing import TYPE_CHECKING, Optional

import requests

from src.constants.task_status import TaskStatus
from src.constants.websocket_actions import WebsocketActions
from src.core.services.config_service import ConfigService
from src.core.web.websocket import WebSocketManager
from src.entity.WebSocketData import WebSocketData
from src.utils.logger import logger

if TYPE_CHECKING:
    from src.main import AppProcessor


config_service = ConfigService()
websocket_manager = WebSocketManager()


@dataclass(frozen=True)
class ResourceRepository:
    name: str
    path: str
    owner: str
    repo: str


class ResourceUpdateService:
    RESOURCE_REPOSITORIES = (
        ResourceRepository(
            name="gakumasu-diff",
            path="assets/gakumasu-diff",
            owner="vertesan",
            repo="gakumasu-diff",
        ),
        ResourceRepository(
            name="GakumasTranslationData",
            path="assets/GakumasTranslationData",
            owner="chinosk6",
            repo="GakumasTranslationData",
        ),
    )
    REQUEST_TIMEOUT = 30
    VERSION_STATE_DIR_NAME = "resource_repository_versions"

    def __init__(self, app: "AppProcessor"):
        self._app = app
        self._started = False
        self._status_lock = Lock()
        self._operation_lock = Lock()
        self._refresh_event = Event()
        self._checker_thread: Optional[Thread] = None
        self._next_check_at: Optional[datetime] = None
        self._status = self._build_empty_status()
        self._session = requests.Session()
        self._git_executable = shutil.which("git")
        self._session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "User-Agent": "gakumas-assistant-resource-updater",
            }
        )
        config_service.add_listener(
            [
                "base.enabled_check_resource_updates",
                "base.check_resource_updates_on_startup",
                "base.resource_update_check_period",
            ],
            self._on_config_changed,
        )

    def start(self):
        if self._started:
            return
        self._started = True
        self._checker_thread = Thread(target=self._checker_loop, daemon=True)
        self._checker_thread.start()

    def get_status(self):
        with self._status_lock:
            return deepcopy(self._status)

    def apply_updates(self):
        if not self._operation_lock.acquire(blocking=False):
            return False, "当前正在检查或更新资源仓库", self.get_status()
        try:
            if self._app.task_queue.queue_status() != TaskStatus.PENDING:
                return False, "任务执行中，无法更新资源仓库", self.get_status()
            self._publish_status(
                {
                    **self.get_status(),
                    "updating": True,
                    "checking": False,
                    "last_error": "",
                }
            )
            current_status = self._check_updates_locked(updating=True)
            repositories_to_update = [
                repo for repo in current_status["repositories"] if repo["has_update"] and not repo["error"]
            ]
            if not repositories_to_update:
                current_status["updating"] = False
                self._publish_status(current_status)
                return True, "资源仓库已经是最新版本", current_status
            for repo_status in repositories_to_update:
                repository = self._get_repository_by_path(repo_status["path"])
                self._update_repository(repository, repo_status["remote_commit"], repo_status["remote_branch"])
            try:
                self._app.reload_game_database()
            except Exception as exc:
                logger.error(f"Reload game database after resource update failed: {exc}")
                current_status = self._check_updates_locked(updating=True)
                current_status["updating"] = False
                current_status["last_error"] = f"资源已更新，但重载游戏数据库失败：{exc}"
                self._publish_status(current_status)
                return False, current_status["last_error"], current_status
            current_status = self._check_updates_locked(
                updating=True,
                reset_timer_on_success=self._is_periodic_check_enabled(),
            )
            if self._is_periodic_check_enabled() and not current_status["last_error"]:
                self._refresh_event.set()
            current_status["updating"] = False
            self._publish_status(current_status)
            return True, "资源仓库更新完成，游戏数据库已重新加载", current_status
        except Exception as exc:
            logger.error(f"Apply resource updates failed: {exc}")
            current_status = self._build_status_from_repositories(
                repositories=self.get_status().get("repositories", []),
                checking=False,
                updating=False,
                last_error=str(exc),
                last_checked_at=self.get_status().get("last_checked_at"),
            )
            self._publish_status(current_status)
            return False, f"资源仓库更新失败：{exc}", current_status
        finally:
            self._operation_lock.release()

    def _checker_loop(self):
        startup_check_pending = True
        while True:
            self._publish_status(self._merge_status_metadata(self.get_status()))
            if startup_check_pending:
                startup_check_pending = False
                if self._should_check_on_startup():
                    self.check_updates(reset_timer_always=self._is_periodic_check_enabled())
                    continue
                self._schedule_next_check()
                self._publish_status(self._merge_status_metadata(self.get_status()))
            if not self._is_periodic_check_enabled():
                if self._wait_for_refresh(60):
                    continue
                continue
            next_check_at = self._ensure_next_check_at()
            wait_seconds = max((next_check_at - datetime.now()).total_seconds(), 0)
            if self._wait_for_refresh(wait_seconds):
                continue
            self.check_updates(reset_timer_always=True)

    def manual_check_updates(self):
        if not self._operation_lock.acquire(blocking=False):
            return False, "当前正在检查或更新资源仓库", self.get_status()
        try:
            status = self._check_updates_locked(reset_timer_on_success=self._is_periodic_check_enabled())
            if self._is_periodic_check_enabled() and not status["last_error"]:
                self._refresh_event.set()
            if status["last_error"]:
                return True, f"资源仓库检查完成，但部分仓库检查失败：{status['last_error']}", status
            if status["has_update"]:
                return True, "资源仓库检查完成，发现可用更新", status
            return True, "资源仓库已经是最新版本", status
        except Exception as exc:
            logger.error(f"Manual resource update check failed: {exc}")
            current_status = self._merge_status_metadata(self.get_status())
            current_status["last_error"] = str(exc)
            self._publish_status(current_status)
            return False, f"资源仓库检查失败：{exc}", current_status
        finally:
            self._operation_lock.release()

    def check_updates(self, reset_timer_on_success: bool = False, reset_timer_always: bool = False):
        if not self._operation_lock.acquire(blocking=False):
            return self.get_status()
        try:
            return self._check_updates_locked(
                reset_timer_on_success=reset_timer_on_success,
                reset_timer_always=reset_timer_always,
            )
        finally:
            self._operation_lock.release()

    def _check_updates_locked(
        self,
        updating: bool = False,
        reset_timer_on_success: bool = False,
        reset_timer_always: bool = False,
    ):
        self._publish_status(
            self._merge_status_metadata({
                **self.get_status(),
                "checking": True,
                "updating": updating,
                "last_error": "",
            })
        )
        repositories = []
        errors = []
        for repository in self.RESOURCE_REPOSITORIES:
            repository_status = self._inspect_repository(repository)
            repositories.append(repository_status)
            if repository_status["error"]:
                errors.append(f"{repository.name}: {repository_status['error']}")
        checked_at = datetime.now()
        if reset_timer_always or (reset_timer_on_success and not errors):
            self._schedule_next_check(checked_at)
        status = self._build_status_from_repositories(
            repositories=repositories,
            checking=False,
            updating=updating,
            last_error="；".join(errors),
            last_checked_at=checked_at.isoformat(timespec="seconds"),
        )
        self._publish_status(status)
        return status

    @staticmethod
    def _now_iso():
        return datetime.now().isoformat(timespec="seconds")

    def _wait_for_refresh(self, timeout_seconds: int):
        if self._refresh_event.wait(timeout=max(timeout_seconds, 0)):
            self._refresh_event.clear()
            return True
        return False

    def _on_config_changed(self, key: str, old_value, new_value):
        logger.info(f"Reload resource update checker because '{key}' changed: {old_value!r} -> {new_value!r}")
        self._set_next_check_at(None)
        self._refresh_event.set()

    def _build_empty_status(self):
        return self._merge_status_metadata({
            "checking": False,
            "updating": False,
            "has_update": False,
            "last_checked_at": None,
            "last_error": "",
            "update_signature": "",
            "repositories": [],
        })

    def _build_status_from_repositories(
        self,
        repositories: list[dict],
        checking: bool,
        updating: bool,
        last_error: str,
        last_checked_at: Optional[str],
    ):
        update_signature = self._build_update_signature(repositories)
        return self._merge_status_metadata({
            "checking": checking,
            "updating": updating,
            "has_update": any(repo["has_update"] and not repo["error"] for repo in repositories),
            "last_checked_at": last_checked_at,
            "last_error": last_error,
            "update_signature": update_signature,
            "repositories": repositories,
        })

    @staticmethod
    def _build_update_signature(repositories: list[dict]):
        changed_repositories = [
            f"{repo['path']}:{repo.get('local_commit', '')}:{repo.get('remote_commit', '')}"
            for repo in repositories
            if repo.get("has_update") and not repo.get("error")
        ]
        if not changed_repositories:
            return ""
        content = "|".join(sorted(changed_repositories)).encode("utf-8")
        import hashlib

        return hashlib.sha1(content).hexdigest()

    def _publish_status(self, status: dict):
        with self._status_lock:
            self._status = deepcopy(status)
            snapshot = deepcopy(self._status)
        websocket_manager.broadcast_action_sync(
            WebsocketActions.ResourceUpdate.StatusChanged,
            WebSocketData(message=snapshot),
        )
        return snapshot

    def _merge_status_metadata(self, status: dict):
        metadata = self._build_status_metadata()
        return {
            **status,
            **metadata,
        }

    def _build_status_metadata(self):
        return {
            "enabled": self._is_periodic_check_enabled(),
            "check_on_startup": self._should_check_on_startup(),
            "check_period": self._get_check_period(),
            "interval_minutes": self._get_check_interval_seconds() // 60,
            "next_check_at": self._get_next_check_at_iso(),
        }

    def _get_check_period(self):
        return str(config_service.base.resource_update_check_period)

    def _get_check_interval_seconds(self):
        period = self._get_check_period()
        return {
            "daily": 24 * 60 * 60,
            "every_3_days": 3 * 24 * 60 * 60,
            "weekly": 7 * 24 * 60 * 60,
        }.get(period, 24 * 60 * 60)

    def _is_periodic_check_enabled(self):
        return bool(config_service.base.enabled_check_resource_updates)

    def _should_check_on_startup(self):
        return bool(config_service.base.check_resource_updates_on_startup)

    def _get_next_check_at(self):
        with self._status_lock:
            return self._next_check_at

    def _get_next_check_at_iso(self):
        next_check_at = self._get_next_check_at()
        if next_check_at is None:
            return None
        return next_check_at.isoformat(timespec="seconds")

    def _set_next_check_at(self, next_check_at: Optional[datetime]):
        with self._status_lock:
            self._next_check_at = next_check_at

    def _schedule_next_check(self, base_time: Optional[datetime] = None):
        if not self._is_periodic_check_enabled():
            self._set_next_check_at(None)
            return None
        if base_time is None:
            base_time = datetime.now()
        next_check_at = base_time + timedelta(seconds=self._get_check_interval_seconds())
        self._set_next_check_at(next_check_at)
        return next_check_at

    def _ensure_next_check_at(self):
        next_check_at = self._get_next_check_at()
        if next_check_at is not None:
            return next_check_at
        scheduled = self._schedule_next_check()
        if scheduled is None:
            raise RuntimeError("Periodic resource update check is not enabled")
        return scheduled

    def _inspect_repository(self, repository: ResourceRepository):
        repo_path = os.path.join(os.getcwd(), repository.path)
        status = {
            "name": repository.name,
            "path": repository.path,
            "exists": os.path.exists(repo_path),
            "dirty": False,
            "has_update": False,
            "local_commit": "",
            "remote_commit": "",
            "local_commit_short": "",
            "remote_commit_short": "",
            "local_branch": "",
            "remote_branch": "",
            "version_source": "",
            "update_method": "",
            "error": "",
        }
        try:
            update_method = self._select_update_method(repo_path)
            if update_method == "git":
                local_version = self._read_local_git_version(repo_path)
                remote_version = self._fetch_remote_git_version(repo_path)
                dirty = self._has_git_dirty_changes(repo_path)
            else:
                local_version = self._read_local_version(repository, repo_path)
                remote_version = self._fetch_remote_version(repository)
                dirty = False
            local_commit = local_version.get("commit", "")
            remote_commit = remote_version.get("commit", "")
            status.update(
                {
                    "dirty": dirty,
                    "local_commit": local_commit,
                    "remote_commit": remote_commit,
                    "local_commit_short": local_commit[:7],
                    "remote_commit_short": remote_commit[:7],
                    "local_branch": local_version.get("branch", ""),
                    "remote_branch": remote_version.get("branch", ""),
                    "version_source": local_version.get("source", ""),
                    "update_method": update_method,
                    "has_update": bool(remote_commit) and (not local_commit or local_commit != remote_commit),
                }
            )
        except Exception as exc:
            status["error"] = str(exc)
        return status

    def _update_repository(self, repository: ResourceRepository, commit_sha: str, branch_name: str):
        repo_path = os.path.join(os.getcwd(), repository.path)
        update_method = self._select_update_method(repo_path)
        if update_method == "git":
            self._update_repository_with_git(repository, repo_path, branch_name)
            updated_version = self._read_local_git_version(repo_path)
            self._write_local_version(
                repository,
                updated_version.get("commit", ""),
                updated_version.get("branch", ""),
                source="git",
            )
            logger.success(
                f"Updated resource repository by git: {repository.path} -> {updated_version.get('commit', '')[:7]}"
            )
            return
        if not commit_sha:
            raise RuntimeError(f"{repository.name} 缺少远端提交信息")
        with tempfile.TemporaryDirectory(prefix=f"{repository.name}_", dir=self._app.data_path) as workdir:
            staged_source = self._download_repository_snapshot(repository, commit_sha, workdir)
            self._replace_repository_directory(repository.path, staged_source)
        self._write_local_version(repository, commit_sha, branch_name, source="snapshot")
        logger.success(f"Updated resource repository: {repository.path} -> {commit_sha[:7]}")

    def _download_repository_snapshot(
        self,
        repository: ResourceRepository,
        commit_sha: str,
        workdir: str,
    ):
        zip_url = f"https://api.github.com/repos/{repository.owner}/{repository.repo}/zipball/{commit_sha}"
        zip_path = os.path.join(workdir, f"{repository.name}.zip")
        response = self._session.get(
            zip_url,
            timeout=self.REQUEST_TIMEOUT,
            stream=True,
            allow_redirects=True,
        )
        if not response.ok:
            raise RuntimeError(self._format_http_error(response))
        with open(zip_path, "wb") as file_obj:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file_obj.write(chunk)
        extract_root = os.path.join(workdir, "extract")
        os.makedirs(extract_root, exist_ok=True)
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(extract_root)
        entries = [
            os.path.join(extract_root, name)
            for name in os.listdir(extract_root)
            if not name.startswith("__MACOSX")
        ]
        if len(entries) == 1 and os.path.isdir(entries[0]):
            return entries[0]
        if entries:
            return extract_root
        raise RuntimeError(f"{repository.name} 下载包解压后为空")

    def _replace_repository_directory(self, relative_path: str, staged_source: str):
        target_path = os.path.join(os.getcwd(), relative_path)
        backup_root = tempfile.mkdtemp(prefix="resource_backup_", dir=self._app.data_path)
        backup_path = os.path.join(backup_root, os.path.basename(target_path))
        try:
            if os.path.exists(target_path):
                shutil.move(target_path, backup_path)
            shutil.move(staged_source, target_path)
        except Exception:
            if os.path.exists(target_path):
                shutil.rmtree(target_path, ignore_errors=True)
            if os.path.exists(backup_path):
                shutil.move(backup_path, target_path)
            shutil.rmtree(backup_root, ignore_errors=True)
            raise
        preserved_git = os.path.join(backup_path, ".git")
        if os.path.exists(preserved_git) and not os.path.exists(os.path.join(target_path, ".git")):
            try:
                shutil.move(preserved_git, os.path.join(target_path, ".git"))
            except Exception as exc:
                logger.warning(f"Preserve git metadata for '{relative_path}' failed: {exc}")
        shutil.rmtree(backup_root, ignore_errors=True)

    def _fetch_remote_version(self, repository: ResourceRepository):
        repo_url = f"https://api.github.com/repos/{repository.owner}/{repository.repo}"
        repo_info = self._get_json(repo_url)
        branch_name = repo_info.get("default_branch") or "main"
        commit_info = self._get_json(f"{repo_url}/commits/{branch_name}")
        commit_sha = commit_info.get("sha", "")
        if not commit_sha:
            raise RuntimeError(f"{repository.name} 未返回默认分支最新提交")
        return {
            "commit": commit_sha,
            "branch": branch_name,
            "source": "github",
        }

    def _read_local_version(self, repository: ResourceRepository, repo_path: str):
        if self._can_use_git(repo_path):
            git_version = self._read_local_git_version(repo_path)
            if git_version:
                return git_version
        metadata = self._read_local_version_metadata(repository)
        if metadata:
            metadata.setdefault("source", "metadata")
            return metadata
        git_version = self._read_git_version(repo_path)
        if git_version:
            return git_version
        return {
            "commit": "",
            "branch": "",
            "source": "unknown",
        }

    def _read_local_version_metadata(self, repository: ResourceRepository):
        metadata_path = self._get_metadata_path(repository)
        if not os.path.exists(metadata_path):
            return None
        with open(metadata_path, "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)
        return {
            "commit": str(data.get("commit", "")),
            "branch": str(data.get("branch", "")),
            "source": "metadata",
        }

    def _write_local_version(
        self,
        repository: ResourceRepository,
        commit_sha: str,
        branch_name: str,
        source: str = "metadata",
    ):
        metadata_path = self._get_metadata_path(repository)
        os.makedirs(os.path.dirname(metadata_path), exist_ok=True)
        with open(metadata_path, "w", encoding="utf-8") as file_obj:
            json.dump(
                {
                    "name": repository.name,
                    "path": repository.path,
                    "owner": repository.owner,
                    "repo": repository.repo,
                    "commit": commit_sha,
                    "branch": branch_name,
                    "source": source,
                    "updated_at": self._now_iso(),
                },
                file_obj,
                ensure_ascii=False,
                indent=2,
            )

    def _get_metadata_path(self, repository: ResourceRepository):
        return os.path.join(
            self._app.data_path,
            self.VERSION_STATE_DIR_NAME,
            f"{repository.name}.json",
        )

    def _select_update_method(self, repo_path: str):
        return "git" if self._can_use_git(repo_path) else "snapshot"

    def _can_use_git(self, repo_path: str):
        return bool(self._git_executable) and bool(self._resolve_git_dir(repo_path))

    def _read_local_git_version(self, repo_path: str):
        if not self._can_use_git(repo_path):
            return self._read_git_version(repo_path)
        commit_sha = self._run_git(["-C", repo_path, "rev-parse", "HEAD"])
        branch_name = self._run_git(["-C", repo_path, "rev-parse", "--abbrev-ref", "HEAD"])
        if branch_name == "HEAD":
            branch_name = self._read_remote_head_branch(repo_path)
        return {
            "commit": commit_sha,
            "branch": branch_name,
            "source": "git",
        }

    def _fetch_remote_git_version(self, repo_path: str):
        output = self._run_git(["-C", repo_path, "ls-remote", "--symref", "origin", "HEAD"])
        branch_name = ""
        commit_sha = ""
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("ref:"):
                parts = line.split()
                if len(parts) >= 3 and parts[-1] == "HEAD":
                    branch_name = parts[1].split("/")[-1]
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[-1] == "HEAD":
                commit_sha = parts[0]
        if not commit_sha:
            raise RuntimeError("无法获取远端 HEAD")
        return {
            "commit": commit_sha,
            "branch": branch_name or self._read_remote_head_branch(repo_path),
            "source": "git",
        }

    def _read_remote_head_branch(self, repo_path: str):
        try:
            output = self._run_git(["-C", repo_path, "symbolic-ref", "--short", "refs/remotes/origin/HEAD"])
        except Exception:
            return ""
        return output.split("/", 1)[-1].strip()

    def _has_git_dirty_changes(self, repo_path: str):
        if not self._can_use_git(repo_path):
            return False
        return bool(self._run_git(["-C", repo_path, "status", "--porcelain"]))

    def _update_repository_with_git(
        self,
        repository: ResourceRepository,
        repo_path: str,
        remote_branch: str = "",
    ):
        remote_branch = remote_branch or self._read_remote_head_branch(repo_path)
        target_ref = f"origin/{remote_branch}" if remote_branch else "FETCH_HEAD"
        # Resource repositories may contain nested submodules that are irrelevant to runtime.
        # Update only the repository itself and never recurse into child submodules.
        base_args = ["-c", "submodule.recurse=false", "-C", repo_path]
        self._run_git([*base_args, "fetch", "--prune", "origin"], timeout=300)
        self._run_git([*base_args, "reset", "--hard", target_ref], timeout=300)
        self._run_git([*base_args, "clean", "-fd"], timeout=300)

    @staticmethod
    def _is_configured_submodule(relative_path: str):
        gitmodules_path = os.path.join(os.getcwd(), ".gitmodules")
        if not os.path.exists(gitmodules_path):
            return False
        with open(gitmodules_path, "r", encoding="utf-8") as file_obj:
            content = file_obj.read()
        return f"path = {relative_path}" in content

    @staticmethod
    def _read_git_version(repo_path: str):
        git_dir = ResourceUpdateService._resolve_git_dir(repo_path)
        if not git_dir:
            return None
        head_path = os.path.join(git_dir, "HEAD")
        if not os.path.exists(head_path):
            return None
        with open(head_path, "r", encoding="utf-8") as file_obj:
            head_value = file_obj.read().strip()
        if not head_value:
            return None
        if head_value.startswith("ref: "):
            ref_name = head_value[5:].strip()
            commit_sha = ResourceUpdateService._read_git_ref(git_dir, ref_name)
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

    @staticmethod
    def _resolve_git_dir(repo_path: str):
        git_entry = os.path.join(repo_path, ".git")
        if os.path.isdir(git_entry):
            return git_entry
        if not os.path.isfile(git_entry):
            return None
        with open(git_entry, "r", encoding="utf-8") as file_obj:
            first_line = file_obj.readline().strip()
        if not first_line.startswith("gitdir:"):
            return None
        git_dir = first_line.split(":", 1)[1].strip()
        if not os.path.isabs(git_dir):
            git_dir = os.path.abspath(os.path.join(repo_path, git_dir))
        return git_dir

    @staticmethod
    def _read_git_ref(git_dir: str, ref_name: str):
        ref_path = os.path.join(git_dir, *ref_name.split("/"))
        if os.path.exists(ref_path):
            with open(ref_path, "r", encoding="utf-8") as file_obj:
                return file_obj.read().strip()
        packed_refs_path = os.path.join(git_dir, "packed-refs")
        if not os.path.exists(packed_refs_path):
            return ""
        with open(packed_refs_path, "r", encoding="utf-8") as file_obj:
            for line in file_obj:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("^"):
                    continue
                try:
                    commit_sha, packed_ref = line.split(" ", 1)
                except ValueError:
                    continue
                if packed_ref == ref_name:
                    return commit_sha.strip()
        return ""

    def _get_repository_by_path(self, relative_path: str):
        repository = next(
            (repo for repo in self.RESOURCE_REPOSITORIES if repo.path == relative_path),
            None,
        )
        if repository is None:
            raise KeyError(f"Unknown resource repository path: {relative_path}")
        return repository

    def _get_json(self, url: str):
        response = self._session.get(url, timeout=self.REQUEST_TIMEOUT)
        if not response.ok:
            raise RuntimeError(self._format_http_error(response))
        return response.json()

    def _run_git(self, args: list[str], timeout: int = 30):
        if not self._git_executable:
            raise RuntimeError("未找到 git，可执行文件")
        result = subprocess.run(
            [self._git_executable, *args],
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            message = stderr or stdout or f"git {' '.join(args)} 执行失败"
            raise RuntimeError(message)
        return (result.stdout or "").strip()

    @staticmethod
    def _format_http_error(response: requests.Response):
        message = ""
        try:
            data = response.json()
            message = data.get("message", "")
        except Exception:
            message = response.text.strip()
        message = message or f"HTTP {response.status_code}"
        return f"GitHub 请求失败（{response.status_code}）：{message}"
