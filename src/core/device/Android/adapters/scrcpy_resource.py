import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parents[5]
SCRCPY_VERSION_PATTERN = re.compile(r"\b[vV]?(\d+\.\d+(?:\.\d+)*)\b")


@dataclass(frozen=True)
class ScrcpyServerResource:
    server_path: Path
    version: str
    source: str

    @classmethod
    def discover(cls) -> Optional["ScrcpyServerResource"]:
        return cls._discover_from_project_bin()

    @classmethod
    def _discover_from_project_bin(cls) -> Optional["ScrcpyServerResource"]:
        bin_dir = PROJECT_ROOT / "bin"
        if not bin_dir.is_dir():
            return None

        candidates = [
            path for path in sorted(bin_dir.glob("scrcpy-server*"), reverse=True)
            if path.is_file()
        ]
        for server_path in candidates:
            version = cls._guess_version(server_path)
            if version:
                return cls(server_path=server_path, version=version, source="project-bin")
        return None

    @classmethod
    def _guess_version(cls, server_path: Path) -> Optional[str]:
        for candidate in (server_path.name, server_path.stem, server_path.parent.name, str(server_path.parent)):
            match = SCRCPY_VERSION_PATTERN.search(candidate)
            if match:
                return match.group(1)
        return None
