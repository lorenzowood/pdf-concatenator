from __future__ import annotations

import fnmatch
import glob as stdglob
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiscoveredPdf:
    path: Path
    relative_path: str


def _normalise_relative(path: Path, base: Path) -> str:
    rel = path.relative_to(base).as_posix()
    return rel


def _matches_any_exclude(relative_path: str, excludes: list[str]) -> bool:
    for pattern in excludes:
        if fnmatch.fnmatch(relative_path, pattern):
            return True
        if fnmatch.fnmatch(Path(relative_path).name, pattern):
            return True
    return False


def _glob_pattern(pattern: str) -> list[Path]:
    path = Path(pattern)
    if path.is_dir():
        return sorted(path.rglob("*.pdf"))
    if any(ch in pattern for ch in "*?[]"):
        return sorted(Path(p) for p in stdglob.glob(pattern, recursive=True))
    if path.is_file() and path.suffix.lower() == ".pdf":
        return [path]
    parent = path.parent if path.parent != Path(".") else Path()
    return sorted(parent.glob(pattern))


def _base_for_pattern(pattern: str, matches: list[Path]) -> Path:
    path = Path(pattern)
    if path.is_dir():
        return path.resolve()

    wildcard_idx = next((i for i, c in enumerate(pattern) if c in "*?[]"), len(pattern))
    prefix = Path(pattern[:wildcard_idx].rstrip("/"))
    if prefix.parts:
        suffix = pattern[wildcard_idx:].lstrip("/")
        if suffix.startswith("**/"):
            after_stars = suffix[3:]
            if after_stars and not any(c in after_stars for c in "*?[]"):
                return prefix.parent.resolve()
        return prefix.resolve()

    if matches:
        return Path(matches[0]).parent.resolve()
    return Path.cwd().resolve()


def discover_pdfs(pattern: str, excludes: list[str] | None = None) -> list[DiscoveredPdf]:
    """Find PDF files matching pattern, sorted by relative path."""
    excludes = excludes or []
    raw_matches = _glob_pattern(pattern)
    pdfs = [p.resolve() for p in raw_matches if p.suffix.lower() == ".pdf" and p.is_file()]
    base = _base_for_pattern(pattern, pdfs)

    results: list[DiscoveredPdf] = []
    for pdf in pdfs:
        try:
            relative = _normalise_relative(pdf, base)
        except ValueError:
            relative = pdf.name
        if _matches_any_exclude(relative, excludes):
            continue
        results.append(DiscoveredPdf(path=pdf, relative_path=relative))

    results.sort(key=lambda r: r.relative_path)
    return results
