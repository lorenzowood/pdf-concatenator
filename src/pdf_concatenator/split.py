from __future__ import annotations

from pathlib import Path

from pdf_concatenator.pdf_build import (
    DocumentInfo,
    PdfBuildError,
    SplitContext,
    _build_pdf_bytes,
    measure_part_size,
)


def part_output_paths(base: Path, total_parts: int) -> list[Path]:
    if total_parts <= 1:
        return [base]
    return [
        base.with_name(f"{base.stem}_part_{part}{base.suffix}")
        for part in range(1, total_parts + 1)
    ]


def _assignment_from_groups(groups: list[list[DocumentInfo]]) -> dict[str, int]:
    assignment: dict[str, int] = {}
    for index, group in enumerate(groups, start=1):
        for doc in group:
            assignment[doc.relative_path] = index
    return assignment


def _plan_parts(
    all_documents: list[DocumentInfo],
    include_summaries: bool,
    max_bytes: int,
) -> list[list[DocumentInfo]]:
    sorted_docs = sorted(all_documents, key=lambda d: d.relative_path)
    groups: list[list[DocumentInfo]] = [[]]

    for doc in sorted_docs:
        trial_groups = groups[:-1] + [groups[-1] + [doc]]
        size = measure_part_size(
            trial_groups,
            all_documents,
            include_summaries,
            part_number=len(trial_groups),
        )
        if groups[-1] and size > max_bytes:
            groups.append([doc])
        else:
            groups[-1] = groups[-1] + [doc]

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
    groups = _plan_parts(all_documents, include_summaries, max_bytes)
    total_parts = len(groups)
    paths = part_output_paths(output_path, total_parts)
    document_parts = _document_parts_from_groups(groups)

    for part_number, (path, part_docs) in enumerate(zip(paths, groups), start=1):
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

    return paths


def parse_max_output_size(value: str) -> int:
    from pdf_concatenator.size_parse import SizeParseError, parse_size

    try:
        return parse_size(value)
    except SizeParseError as exc:
        raise PdfBuildError(str(exc)) from exc
