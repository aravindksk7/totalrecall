"""Runtime path mapping helpers for repository learning scans."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath


@dataclass(frozen=True)
class LearningPathResolution:
    path: str
    warnings: list[str]


def resolve_learning_path(
    requested_path: str,
    path_mappings: dict[str, str],
) -> LearningPathResolution:
    """Translate a submitted host path to a runtime-visible path when configured."""
    clean_path = requested_path.strip()
    if not clean_path or not path_mappings:
        return LearningPathResolution(path=clean_path, warnings=[])

    candidate = _normalise_for_match(clean_path)
    candidate_cmp = _comparison_value(clean_path, candidate)

    ordered_mappings = sorted(
        path_mappings.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for source, target in ordered_mappings:
        clean_source = source.strip()
        clean_target = target.strip()
        if not clean_source or not clean_target:
            continue

        source_norm = _normalise_for_match(clean_source)
        source_cmp = _comparison_value(clean_source, source_norm)
        if candidate_cmp != source_cmp and not candidate_cmp.startswith(f"{source_cmp}/"):
            continue

        suffix = candidate[len(source_norm) :].lstrip("/")
        mapped_path = _join_mapped_path(clean_target, suffix)
        return LearningPathResolution(
            path=mapped_path,
            warnings=[
                (
                    "Mapped learning path from "
                    f"{clean_path} to {mapped_path} using configured path mapping "
                    f"{clean_source} -> {clean_target}."
                )
            ],
        )

    return LearningPathResolution(path=clean_path, warnings=[])


def _normalise_for_match(value: str) -> str:
    return value.strip().replace("\\", "/").rstrip("/")


def _comparison_value(original: str, normalised: str) -> str:
    if _looks_like_windows_path(original):
        return normalised.casefold()
    return normalised


def _looks_like_windows_path(value: str) -> bool:
    return "\\" in value or (len(value) >= 2 and value[1] == ":")


def _join_mapped_path(target: str, suffix: str) -> str:
    parts = [part for part in suffix.split("/") if part]
    clean_target = target.rstrip("\\/")
    if _looks_like_windows_path(clean_target):
        return str(PureWindowsPath(clean_target, *parts))
    if clean_target.startswith("/"):
        return str(PurePosixPath(clean_target, *parts))
    return str(Path(clean_target, *parts))
