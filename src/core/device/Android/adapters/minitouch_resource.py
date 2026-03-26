from dataclasses import dataclass
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parents[5]


@dataclass(frozen=True)
class MinitouchBinaryResource:
    local_path: Path
    abi: str
    binary_name: str
    source: str

    @classmethod
    def discover(cls, abi_list: list[str], sdk: int) -> Optional["MinitouchBinaryResource"]:
        binary_name = "minitouch" if sdk >= 16 else "minitouch-nopie"
        root = PROJECT_ROOT / "bin" / "minitouch"
        candidate_roots = [
            root / "libs",
            root,
        ]

        for base in candidate_roots:
            for abi in abi_list:
                local_path = base / abi / binary_name
                if local_path.is_file():
                    return cls(
                        local_path=local_path,
                        abi=abi,
                        binary_name=binary_name,
                        source="project-bin",
                    )
        return None
