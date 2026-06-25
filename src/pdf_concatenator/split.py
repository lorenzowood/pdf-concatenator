from __future__ import annotations

import sys
from pathlib import Path

from tqdm import tqdm

from pdf_concatenator.pdf_build import (
    DocumentInfo,
    PdfBuildError,
    SplitContext,
    _build_pdf_bytes,
    measure_part_size,
)
from pdf_concatenator.size_estimate import estimate_part_bytes, estimate_total_parts


def part_output_paths(base: Path, total_parts: int) -> list[Path]:
    if total_parts <= 1:
        return [base]
    return [
        base.with_name(f"{base.stem}_part_{part}{base.suffix}")
        for part in range(1, total_parts + 1)
    ]


def _plan_parts(
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

    return _rebalance_groups(groups, all_documents, include_summaries, max_bytes)


def _rebalance_groups(
    groups: list[list[DocumentInfo]],
    all_documents: list[DocumentInfo],
    include_summaries: bool,
    max_bytes: int,
) -> list[list[DocumentInfo]]:
    index = 0
    while index < len(groups):
        while True:
            size = measure_part_size(
                groups,
                all_documents,
                include_summaries,
                part_number=index + 1,
            )
            if size <= max_bytes:
                break
            if len(groups[index]) <= 1:
                doc = groups[index][0]
                raise PdfBuildError(
                    f"Document {doc.relative_path} exceeds max output size "
                    f"({max_bytes} bytes) even on its own"
                )
            moved = groups[index].pop()
            if index + 1 < len(groups):
                groups[index + 1].insert(0, moved)
            else:
                groups.append([moved])
        index += 1
    return [group for group in groups if group]


def _document_parts_from_groups(
    groups: list[list[DocumentInfo]],
) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for index, group in enumerate(groups, start=1):
        for doc in group:
            mapping[doc.relative_path] = index
    return mapping


def build_split_outputs(
    all_documents: list[DocumentInfo],
    output_path: Path,
    include_summaries: bool,
    max_bytes: int,
) -> list[Path]:
    print("Planning parts by size...", file=sys.stderr, flush=True)
    groups = _plan_parts(all_documents, include_summaries, max_bytes)
    total_parts = len(groups)
    paths = part_output_paths(output_path, total_parts)
    document_parts = _document_parts_from_groups(groups)

    if total_parts > 1:
        print(
            f"Verifying and building {total_parts} parts...",
            file=sys.stderr,
            flush=True,
        )

    progress = tqdm(
        list(enumerate(zip(paths, groups), start=1)),
        desc="Building parts",
        unit="part",
        disable=not sys.stderr.isatty(),
        file=sys.stderr,
    )
    written: list[Path] = []
    for part_number, (path, part_docs) in progress:
        split = SplitContext(
            part_number=part_number,
            total_parts=total_parts,
            document_parts=document_parts,
        )
        path.write_bytes(
            _build_pdf_bytes(
                part_docs,
                include_summaries,
                all_documents=all_documents,
                split=split if total_parts > 1 else None,
            )
        )
        if path.stat().st_size > max_bytes:
            raise PdfBuildError(f"Output part exceeds max size: {path.name}")
        written.append(path)
        progress.set_postfix_str(path.name, refresh=False)

    return written


def parse_max_output_size(value: str) -> int:
    from pdf_concatenator.size_parse import SizeParseError, parse_size

    try:
        return parse_size(value)
    except SizeParseError as exc:
        raise PdfBuildError(str(exc)) from exc
