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
ROW_HEIGHT = 16
INDENT_PER_LEVEL = 14
GREY = colors.Color(0.95, 0.95, 0.95)


@dataclass(frozen=True)
class DocumentInfo:
    path: Path
    relative_path: str
    title: str
    summary: str | None


@dataclass
class _TocNode:
    name: str
    is_file: bool
    page: int | None = None
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
    rows: list[tuple[int, str, bool, int | None, str | None]],
) -> None:
    for child in sorted(node.children, key=lambda n: (n.is_file, n.name)):
        label = child.name if child.is_file else f"{child.name}/"
        rows.append((depth, label, child.is_file, child.page, child.summary))
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


def _render_toc_pages(
    rows: list[tuple[int, str, bool, int | None, str | None]],
    include_summaries: bool,
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
            return y - 28
        return y

    c = canvas.Canvas(buffer, pagesize=letter)
    y = start_page(c)

    for depth, label, is_file, page_num, summary in rows:
        summary_lines = 0
        if include_summaries and is_file and summary:
            summary_lines = len(_wrap_text(summary, 70))

        block_height = ROW_HEIGHT + summary_lines * 12
        if y - block_height < MARGIN:
            c.showPage()
            y = start_page(c)

        if row_index % 2 == 1:
            c.setFillColor(GREY)
            c.rect(0, y - block_height + 4, PAGE_WIDTH, block_height, fill=1, stroke=0)
            c.setFillColor(colors.black)

        x = MARGIN + depth * INDENT_PER_LEVEL
        c.setFont("Helvetica", 11)
        c.drawString(x, y, label)
        if is_file and page_num is not None:
            c.drawRightString(PAGE_WIDTH - MARGIN, y, str(page_num))

        line_y = y - 12
        if include_summaries and is_file and summary:
            c.setFont("Helvetica", 9)
            for line in _wrap_text(summary, 70):
                c.drawString(x + INDENT_PER_LEVEL, line_y, line)
                line_y -= 12

        y -= block_height
        row_index += 1

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
    c.drawRightString(PAGE_WIDTH - MARGIN, MARGIN, str(page_number))
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


def _set_file_page(root: _TocNode, relative_path: str, page: int) -> None:
    parts = relative_path.split("/")
    node = root
    for part in parts:
        node = next(child for child in node.children if child.name == part)
    if node.is_file:
        node.page = page


def build_concatenated_pdf(
    documents: list[DocumentInfo],
    output_path: Path,
    include_summaries: bool,
) -> None:
    if not documents:
        raise PdfBuildError("No documents to concatenate")

    root = _build_toc_tree(documents, include_summaries)
    toc_page_count = 1
    toc_reader: PdfReader | None = None

    for _ in range(10):
        cover_pages = _assign_cover_pages(documents, toc_page_count)
        for doc in documents:
            _set_file_page(root, doc.relative_path, cover_pages[doc.relative_path])

        rows: list[tuple[int, str, bool, int | None, str | None]] = []
        _flatten_toc_rows(root, 0, rows)
        toc_reader = _render_toc_pages(rows, include_summaries)
        actual = len(toc_reader.pages)
        if actual == toc_page_count:
            break
        toc_page_count = actual
    else:
        raise PdfBuildError("Could not stabilise table of contents page count")

    assert toc_reader is not None
    cover_pages = _assign_cover_pages(documents, len(toc_reader.pages))
    for doc in documents:
        _set_file_page(root, doc.relative_path, cover_pages[doc.relative_path])
    rows = []
    _flatten_toc_rows(root, 0, rows)
    toc_reader = _render_toc_pages(rows, include_summaries)

    writer = PdfWriter()
    for page in toc_reader.pages:
        writer.add_page(page)

    for doc in sorted(documents, key=lambda d: d.relative_path):
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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as handle:
        writer.write(handle)
