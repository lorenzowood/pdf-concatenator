from __future__ import annotations

from pdf_concatenator.pdf_build import DocumentInfo

COVER_PAGE_ESTIMATE = 3_000
TOC_BASE_ESTIMATE = 12_000
TOC_ROW_ESTIMATE = 200
SPLIT_NOTICE_ESTIMATE = 500
MERGE_OVERHEAD_RATIO = 1.08


def estimate_total_parts(
    groups: list[list[DocumentInfo]],
    all_documents: list[DocumentInfo],
) -> int:
    assigned = sum(1 for group in groups for _ in group)
    if assigned < len(all_documents):
        return max(2, len([group for group in groups if group]) + 1)
    return max(1, len([group for group in groups if group]))


def estimate_part_bytes(
    part_documents: list[DocumentInfo],
    all_documents: list[DocumentInfo],
    include_summaries: bool,
    *,
    total_parts: int,
) -> int:
    if not part_documents:
        return 0

    toc_bytes = TOC_BASE_ESTIMATE + len(all_documents) * TOC_ROW_ESTIMATE
    if include_summaries:
        toc_bytes += sum(len(doc.summary or "") * 6 for doc in all_documents)
    if total_parts > 1:
        toc_bytes += SPLIT_NOTICE_ESTIMATE

    cover_bytes = len(part_documents) * COVER_PAGE_ESTIMATE
    source_bytes = sum(doc.path.stat().st_size for doc in part_documents)
    total = toc_bytes + cover_bytes + source_bytes
    return int(total * MERGE_OVERHEAD_RATIO)
