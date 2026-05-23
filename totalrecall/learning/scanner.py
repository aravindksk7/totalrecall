"""Read-only bounded file scanner for learning runs."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

_LANGUAGE_MAP: dict[str, str] = {".py": "python", ".ts": "typescript"}
_MAX_FILE_BYTES = 256 * 1024  # 256 KB — skip very large files


@dataclass(frozen=True)
class ScannedFile:
    path: Path
    content: str
    content_hash: str
    language: str


def scan_path(root: Path, max_files: int = 500) -> list[ScannedFile]:
    """Walk root read-only; return Python and TypeScript source files up to max_files."""
    files: list[ScannedFile] = []

    for file_path in sorted(root.rglob("*")):
        if len(files) >= max_files:
            break
        if not file_path.is_file():
            continue
        language = _LANGUAGE_MAP.get(file_path.suffix.lower())
        if language is None:
            continue
        try:
            if file_path.stat().st_size > _MAX_FILE_BYTES:
                continue
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        content_hash = hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()
        files.append(
            ScannedFile(
                path=file_path, content=content, content_hash=content_hash, language=language
            )
        )

    return files
