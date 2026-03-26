from dataclasses import dataclass
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parents[5]


@dataclass(frozen=True)
class MaaTouchResource:
    local_path: Path
    source: str

    @classmethod
    def discover(cls) -> Optional["MaaTouchResource"]:
        candidates = [
            PROJECT_ROOT / "bin" / "maatouch" / "maatouch",
            PROJECT_ROOT / "bin" / "maatouch" / "maatouch.apk",
            PROJECT_ROOT / "bin" / "maatouch.apk",
        ]

        for local_path in candidates:
            if local_path.is_file():
                return cls(local_path=local_path, source="project-bin")
        return None
