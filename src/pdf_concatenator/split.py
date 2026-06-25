from __future__ import annotations

import sys
from pathlib import Path

from pdf_concatenator.pdf_build import (
    DocumentInfo,
    PdfBuildError,
    SplitContext,
    _build_pdf_bytes,
)
from pdf_concatenator.size_estimate import estimate_part_bytes, estimate_total_parts


def part_output_paths(base: Path, total_parts: int) -> list[Path]:
    if total_parts <= 1:
        return [base]
    return [
        base.with_name(f"{base.stem}_part_{part}{base.suffix}")
        for part in range(1, total_parts + 1)
    ]


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _greedy_plan(
    all_documents: list[DocumentInfo],
    include_summaries: bool,
    max_bytes: int,
) -> list[list[DocumentInfo]]:
    sorted_docs = sorted(all_documents, key=lambda d: d.relative_path)
    groups: list[list[DocumentInfo]] = [[]]

    for doc in sorted_docs:
        trial = groups[-1] + [doc]
        trial_groups = groups[:-1] + [trial]
        total_parts = estimate_total_parts(trial_groups, all_documents)
        size = estimate_part_bytes(
            trial,
            all_documents,
            include_summaries,
            total_parts=total_parts,
        )
        if groups[-1] and size > max_bytes:
            groups.append([doc])
        else:
            groups[-1] = trial

    return [group for group in groups if group]


def _document_parts_from_groups(
    groups: list[list[DocumentInfo]],
) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for index, group in enumerate(groups, start=1):
        for doc in group:
            mapping[doc.relative_path] = index
    return mapping


def _build_part_bytes(
    groups: list[list[DocumentInfo]],
    all_documents: list[DocumentInfo],
    include_summaries: bool,
    part_number: int,
) -> bytes:
    total_parts = len(groups)
    part_docs = groups[part_number - 1]
    split = None
    if total_parts > 1:
        split = SplitContext(
            part_number=part_number,
            total_parts=total_parts,
            document_parts=_document_parts_from_groups(groups),
        )
    return _build_pdf_bytes(
        part_docs,
        include_summaries,
        all_documents=all_documents,
        split=split,
    )


def _build_and_rebalance(
    groups: list[list[DocumentInfo]],
    all_documents: list[DocumentInfo],
    include_summaries: bool,
    max_bytes: int,
) -> list[bytes]:
    built: list[bytes | None] = [None] * len(groups)
    index = 0

    while index < len(groups):
        attempts = 0
        while True:
            attempts += 1
            suffix = f" (attempt {attempts})" if attempts > 1 else ""
            _log(f"Building part {index + 1} of {len(groups)}{suffix}...")
            data = _build_part_bytes(
                groups,
                all_documents,
                include_summaries,
                part_number=index + 1,
            )
            if len(data) <= max_bytes:
                built[index] = data
                break

            if len(groups[index]) <= 1:
                doc = groups[index][0]
                raise PdfBuildError(
                    f"Document {doc.relative_path} exceeds max output size "
                    f"({max_bytes} bytes) even on its own"
                )

            for slot in range(index, len(built)):
                built[slot] = None
            moved = groups[index].pop()
            if index + 1 < len(groups):
                groups[index + 1].insert(0, moved)
            else:
                groups.append([moved])
                built.append(None)

        index += 1

    return [data for data in built if data is not None]


def build_split_outputs(
    all_documents: list[DocumentInfo],
    output_path: Path,
    include_summaries: bool,
    max_bytes: int,
) -> list[Path]:
    _log("Planning parts by size...")
    groups = _greedy_plan(all_documents, include_summaries, max_bytes)
    total_parts = len(groups)

    if total_parts > 1:
        _log(f"Building {total_parts} parts...")
    else:
        _log("Building output PDF...")

    part_bytes = _build_and_rebalance(
        groups,
        all_documents,
        include_summaries,
        max_bytes,
    )
    paths = part_output_paths(output_path, total_parts)

    written: list[Path] = []
    for path, data in zip(paths, part_bytes):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        written.append(path)
        size = len(data)
        if size >= 1024 * 1024:
            _log(f"Wrote {path.name} ({size / (1024 * 1024):.1f} MB)")
        else:
            _log(f"Wrote {path.name} ({size // 1024} KB)")

    return written


def parse_max_output_size(value: str) -> int:
    from pdf_concatenator.size_parse import SizeParseError, parse_size

    try:
        return parse_size(value)
    except SizeParseError as exc:
        raise PdfBuildError(str(exc)) from exc
