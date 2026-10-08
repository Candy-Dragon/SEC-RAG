"""Create output directories on demand (no empty folder tree upfront)."""

from pathlib import Path


def ensure_parent_dir(file_path: Path) -> Path:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    return file_path
