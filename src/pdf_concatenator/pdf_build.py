from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


PAGE_WIDTH, PAGE_HEIGHT = letter
MARGIN = 54  # 0.75 inch
FOOTER_HEIGHT = 14
CONTENT_BOTTOM = MARGIN + FOOTER_HEIGHT
ROW_HEIGHT = 16
LABEL_BASELINE_FROM_TOP = 12
SUMMARY_LINE_HEIGHT = 12
INDENT_PER_LEVEL = 14
GREY = colors.Color(0.95, 0.95, 0.95)
SUMMARY_DISCLAIMER = "Summaries are generated automatically and may contain errors."


@dataclass(frozen=True)
class DocumentInfo:
    path: Path
    relative_path: str
    title: str
    summary: str | None


@dataclass(frozen=True)
class SplitContext:
    part_number: int
    total_parts: int
    document_parts: dict[str, int]


@dataclass
class _TocNode:
    name: str
    is_file: bool
    page: int | None = None
    other_part: int | None = None
    summary: str | None = None
    children: list[_TocNode] = field(default_factory=list)


class PdfBuildError(Exception):
    pass


def _source_page_count(path: Path) -> int:
    try:
        reader = PdfReader(str(path))
        return len(reader.pages)
    except Exception as exc:
        raise PdfBuildError(f"Failed to read PDF: {path}") from exc


def _build_toc_tree(
    documents: list[DocumentInfo], include_summaries: bool
) -> _TocNode:
    root = _TocNode(name="", is_file=False)
    for doc in sorted(documents, key=lambda d: d.relative_path):
        parts = doc.relative_path.split("/")
        node = root
        for index, part in enumerate(parts):
            is_file = index == len(parts) - 1
            existing = next(
                (child for child in node.children if child.name == part),
                None,
            )
            if existing is None:
                existing = _TocNode(name=part, is_file=is_file)
                node.children.append(existing)
            node = existing
        if include_summaries and doc.summary:
            node.summary = doc.summary
    return root


def _flatten_toc_rows(
    node: _TocNode,
    depth: int,
    rows: list[tuple[int, str, bool, str | None, str | None]],
) -> None:
    for child in sorted(node.children, key=lambda n: (n.is_file, n.name)):
        label = child.name if child.is_file else f"{child.name}/"
        right_column: str | None = None
        if child.is_file:
            if child.page is not None:
                right_column = str(child.page)
            elif child.other_part is not None:
                right_column = f"Part {child.other_part}"
        rows.append((depth, label, child.is_file, right_column, child.summary))
        if not child.is_file:
            _flatten_toc_rows(child, depth + 1, rows)


def _wrap_text(text: str, max_chars: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join(current + [word])
        if current and len(candidate) > max_chars:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines or [""]


def _row_block_height(
    is_file: bool,
    summary: str | None,
    include_summaries: bool,
) -> int:
    height = ROW_HEIGHT
    if include_summaries and is_file and summary:
        height += len(_wrap_text(summary, 70)) * SUMMARY_LINE_HEIGHT
    return height


def _draw_page_footer(
    c: canvas.Canvas, page_number: int, *, include_summaries: bool
) -> None:
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.black)
    if include_summaries:
        c.drawString(MARGIN, MARGIN, SUMMARY_DISCLAIMER)
    c.drawRightString(PAGE_WIDTH - MARGIN, MARGIN, str(page_number))


def _render_toc_pages(
    rows: list[tuple[int, str, bool, str | None, str | None]],
    include_summaries: bool,
    *,
    split: SplitContext | None = None,
) -> PdfReader:
    buffer = io.BytesIO()
    page_count = 0
    row_index = 0
    y = PAGE_HEIGHT - MARGIN

    def start_page(c: canvas.Canvas) -> float:
        nonlocal page_count, y
        page_count += 1
        y = PAGE_HEIGHT - MARGIN
        if page_count == 1:
            c.setFont("Helvetica-Bold", 16)
            c.drawString(MARGIN, y, "Contents")
            y -= 28
            if split is not None and split.total_parts > 1:
                c.setFont("Helvetica", 11)
                notice = (
                    f"This archive is split into {split.total_parts} parts. "
                    f"This is part {split.part_number}."
                )
                for line in _wrap_text(notice, 80):
                    c.drawString(MARGIN, y, line)
                    y -= 14
                y -= 8
            return y
        return y

    def end_page(c: canvas.Canvas) -> None:
        _draw_page_footer(c, page_count, include_summaries=include_summaries)

    c = canvas.Canvas(buffer, pagesize=letter)
    y = start_page(c)

    for depth, label, is_file, right_column, summary in rows:
        block_height = _row_block_height(is_file, summary, include_summaries)
        if y - block_height < CONTENT_BOTTOM:
            end_page(c)
            c.showPage()
            y = start_page(c)

        row_top = y
        row_bottom = y - block_height

        if row_index % 2 == 1:
            c.setFillColor(GREY)
            c.rect(0, row_bottom, PAGE_WIDTH, block_height, fill=1, stroke=0)
            c.setFillColor(colors.black)

        x = MARGIN + depth * INDENT_PER_LEVEL
        label_baseline = row_top - LABEL_BASELINE_FROM_TOP
        c.setFont("Helvetica", 11)
        c.drawString(x, label_baseline, label)
        if is_file and right_column is not None:
            c.drawRightString(PAGE_WIDTH - MARGIN, label_baseline, right_column)

        summary_baseline = label_baseline - SUMMARY_LINE_HEIGHT
        if include_summaries and is_file and summary:
            c.setFont("Helvetica", 9)
            for line in _wrap_text(summary, 70):
                c.drawString(x + INDENT_PER_LEVEL, summary_baseline, line)
                summary_baseline -= SUMMARY_LINE_HEIGHT

        y = row_bottom
        row_index += 1

    end_page(c)
    c.save()
    buffer.seek(0)
    return PdfReader(buffer)


def _render_cover_page(
    relative_path: str,
    summary: str | None,
    page_number: int,
    include_summaries: bool,
) -> PdfReader:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.setFont("Helvetica-Bold", 14)
    y = PAGE_HEIGHT - MARGIN
    for line in _wrap_text(relative_path, 60):
        c.drawString(MARGIN, y, line)
        y -= 18

    if include_summaries and summary:
        y -= 12
        c.setFont("Helvetica", 11)
        for line in _wrap_text(summary, 70):
            c.drawString(MARGIN, y, line)
            y -= 14

    c.setFont("Helvetica", 10)
    _draw_page_footer(c, page_number, include_summaries=include_summaries)
    c.showPage()
    c.save()
    buffer.seek(0)
    return PdfReader(buffer)


def _assign_cover_pages(
    documents: list[DocumentInfo],
    toc_page_count: int,
) -> dict[str, int]:
    page = toc_page_count + 1
    cover_pages: dict[str, int] = {}
    for doc in sorted(documents, key=lambda d: d.relative_path):
        cover_pages[doc.relative_path] = page
        page += 1 + _source_page_count(doc.path)
    return cover_pages


def _find_file_node(root: _TocNode, relative_path: str) -> _TocNode:
    parts = relative_path.split("/")
    node = root
    for part in parts:
        node = next(child for child in node.children if child.name == part)
    return node


def _build_pdf_bytes(
    part_documents: list[DocumentInfo],
    include_summaries: bool,
    *,
    all_documents: list[DocumentInfo] | None = None,
    split: SplitContext | None = None,
) -> bytes:
    if not part_documents:
        raise PdfBuildError("No documents to concatenate")

    toc_documents = all_documents or part_documents
    root = _build_toc_tree(toc_documents, include_summaries)
    toc_page_count = 1
    toc_reader: PdfReader | None = None

    for _ in range(10):
        cover_pages = _assign_cover_pages(part_documents, toc_page_count)
        for doc in toc_documents:
            node = _find_file_node(root, doc.relative_path)
            node.page = None
            node.other_part = None
            if doc.relative_path in cover_pages:
                node.page = cover_pages[doc.relative_path]
            elif split is not None:
                node.other_part = split.document_parts[doc.relative_path]

        rows: list[tuple[int, str, bool, str | None, str | None]] = []
        _flatten_toc_rows(root, 0, rows)
        toc_reader = _render_toc_pages(rows, include_summaries, split=split)
        actual = len(toc_reader.pages)
        if actual == toc_page_count:
            break
        toc_page_count = actual
    else:
        raise PdfBuildError("Could not stabilise table of contents page count")

    assert toc_reader is not None
    cover_pages = _assign_cover_pages(part_documents, len(toc_reader.pages))
    for doc in toc_documents:
        node = _find_file_node(root, doc.relative_path)
        node.page = None
        node.other_part = None
        if doc.relative_path in cover_pages:
            node.page = cover_pages[doc.relative_path]
        elif split is not None:
            node.other_part = split.document_parts[doc.relative_path]

    rows = []
    _flatten_toc_rows(root, 0, rows)
    toc_reader = _render_toc_pages(rows, include_summaries, split=split)

    writer = PdfWriter()
    for page in toc_reader.pages:
        writer.add_page(page)

    for doc in sorted(part_documents, key=lambda d: d.relative_path):
        cover_num = cover_pages[doc.relative_path]
        cover_reader = _render_cover_page(
            doc.relative_path,
            doc.summary,
            cover_num,
            include_summaries,
        )
        writer.add_page(cover_reader.pages[0])
        source = PdfReader(str(doc.path))
        for page in source.pages:
            writer.add_page(page)

    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def build_concatenated_pdf(
    documents: list[DocumentInfo],
    output_path: Path,
    include_summaries: bool,
    *,
    all_documents: list[DocumentInfo] | None = None,
    split: SplitContext | None = None,
) -> None:
    data = _build_pdf_bytes(
        documents,
        include_summaries,
        all_documents=all_documents,
        split=split,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)


def _split_context_for_groups(
    groups: list[list[DocumentInfo]],
    all_documents: list[DocumentInfo],
    part_number: int,
) -> SplitContext | None:
    assignment: dict[str, int] = {}
    next_part_index = 1
    for group in groups:
        if not group:
            continue
        for doc in group:
            assignment[doc.relative_path] = next_part_index
        next_part_index += 1

    unassigned = [
        doc for doc in all_documents if doc.relative_path not in assignment
    ]
    if not unassigned and next_part_index - 1 <= 1:
        return None

    total_parts = (next_part_index - 1) + (1 if unassigned else 0)
    if total_parts <= 1:
        return None

    for doc in unassigned:
        assignment[doc.relative_path] = total_parts

    return SplitContext(
        part_number=part_number,
        total_parts=total_parts,
        document_parts=assignment,
    )


def measure_part_size(
    groups: list[list[DocumentInfo]],
    all_documents: list[DocumentInfo],
    include_summaries: bool,
    part_number: int,
) -> int:
    part_documents = groups[part_number - 1]
    split = _split_context_for_groups(groups, all_documents, part_number)
    return len(
        _build_pdf_bytes(
            part_documents,
            include_summaries,
            all_documents=all_documents,
            split=split,
        )
    )
