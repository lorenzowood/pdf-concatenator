from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PageObject, PdfReader, PdfWriter
from pdf_concatenator.color_parse import DEFAULT_BACKGROUND_RGB, tint_with_black
from pdf_concatenator.page_size import (
    DEFAULT_INDEX_PAGE_SIZE,
    DEFAULT_SEPARATOR_PAGE_SIZE,
    PageSize,
    closest_page_size,
    effective_page_size,
    snap_page_to_size,
)
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas


@dataclass(frozen=True)
class PageLayout:
    page_size: PageSize
    margin: float = 54
    footer_height: float = 14
    row_height: float = 16
    label_line_height: float = 14
    label_baseline_from_top: float = 12
    summary_line_height: float = 12
    row_bottom_padding: float = 4
    indent_per_level: float = 14
    right_column_reserve: float = 52

    @property
    def width(self) -> float:
        return self.page_size.width

    @property
    def height(self) -> float:
        return self.page_size.height

    @property
    def content_bottom(self) -> float:
        return self.margin + self.footer_height


@dataclass(frozen=True)
class PageSizeOptions:
    allowed_sizes: tuple[PageSize, ...] = ()
    index_page_size: PageSize | None = None
    separator_page_size: PageSize | None = None

    @property
    def snapping_enabled(self) -> bool:
        return bool(self.allowed_sizes)


DEFAULT_PAGE_LAYOUT = PageLayout(DEFAULT_INDEX_PAGE_SIZE)
PAGE_WIDTH = DEFAULT_PAGE_LAYOUT.width
PAGE_HEIGHT = DEFAULT_PAGE_LAYOUT.height
MARGIN = DEFAULT_PAGE_LAYOUT.margin
FOOTER_HEIGHT = DEFAULT_PAGE_LAYOUT.footer_height
CONTENT_BOTTOM = DEFAULT_PAGE_LAYOUT.content_bottom
ROW_HEIGHT = DEFAULT_PAGE_LAYOUT.row_height
LABEL_LINE_HEIGHT = DEFAULT_PAGE_LAYOUT.label_line_height
LABEL_BASELINE_FROM_TOP = DEFAULT_PAGE_LAYOUT.label_baseline_from_top
SUMMARY_LINE_HEIGHT = DEFAULT_PAGE_LAYOUT.summary_line_height
ROW_BOTTOM_PADDING = DEFAULT_PAGE_LAYOUT.row_bottom_padding
INDENT_PER_LEVEL = DEFAULT_PAGE_LAYOUT.indent_per_level
RIGHT_COLUMN_RESERVE = DEFAULT_PAGE_LAYOUT.right_column_reserve
LABEL_FONT = "Helvetica"
LABEL_FONT_SIZE = 11
SUMMARY_FONT = "Helvetica"
SUMMARY_FONT_SIZE = 9
ROW_STRIPE_BLACK_OPACITY = 0.05
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


def _layout_for_page_size(page_size: PageSize) -> PageLayout:
    return PageLayout(page_size)


def _resolve_index_page_size(
    page_size_options: PageSizeOptions,
    first_document_size: PageSize | None,
) -> PageSize:
    if page_size_options.index_page_size is not None:
        return page_size_options.index_page_size
    if page_size_options.snapping_enabled and first_document_size is not None:
        return first_document_size
    return DEFAULT_INDEX_PAGE_SIZE


def _resolve_separator_page_size(
    page_size_options: PageSizeOptions,
    document_size: PageSize | None,
) -> PageSize:
    if page_size_options.separator_page_size is not None:
        return page_size_options.separator_page_size
    if page_size_options.snapping_enabled and document_size is not None:
        return document_size
    return DEFAULT_SEPARATOR_PAGE_SIZE


def _document_target_sizes(
    documents: list[DocumentInfo],
    page_size_options: PageSizeOptions,
) -> dict[str, PageSize]:
    if not page_size_options.snapping_enabled:
        return {}

    sizes: dict[str, PageSize] = {}
    for doc in documents:
        try:
            reader = PdfReader(str(doc.path))
            if not reader.pages:
                raise PdfBuildError(f"PDF has no pages: {doc.path}")
            width, height = effective_page_size(reader.pages[0])
            sizes[doc.relative_path] = closest_page_size(
                width, height, page_size_options.allowed_sizes
            )
        except PdfBuildError:
            raise
        except Exception as exc:
            raise PdfBuildError(f"Failed to read PDF: {doc.path}") from exc
    return sizes


def _snap_page_if_needed(
    page: PageObject,
    page_size_options: PageSizeOptions,
) -> PageObject:
    if not page_size_options.snapping_enabled:
        return page
    width, height = effective_page_size(page)
    target = closest_page_size(width, height, page_size_options.allowed_sizes)
    return snap_page_to_size(page, target)


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


def _text_width(font_name: str, font_size: float, text: str) -> float:
    return pdfmetrics.stringWidth(text, font_name, font_size)


def _wrap_text_to_width(
    text: str,
    font_name: str,
    font_size: float,
    max_width: float,
) -> list[str]:
    if max_width <= 0:
        return [text]

    words = text.split()
    lines: list[str] = []
    current: list[str] = []

    for word in words:
        candidate = " ".join(current + [word]) if current else word
        if current and _text_width(font_name, font_size, candidate) > max_width:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)

    if current:
        remainder = " ".join(current)
        if _text_width(font_name, font_size, remainder) > max_width:
            lines.extend(_wrap_text(remainder, max(1, int(max_width / (font_size * 0.5)))))
        else:
            lines.append(remainder)

    return lines or [""]


def _text_area_width(layout: PageLayout, x: float, has_right_column: bool) -> float:
    right_edge = layout.width - layout.margin
    if has_right_column:
        right_edge -= layout.right_column_reserve
    return right_edge - x


def _label_lines(
    layout: PageLayout,
    depth: int,
    label: str,
    is_file: bool,
    right_column: str | None,
) -> list[str]:
    x = layout.margin + depth * layout.indent_per_level
    reserve_column = is_file and right_column is not None
    width = _text_area_width(layout, x, reserve_column)
    return _wrap_text_to_width(label, LABEL_FONT, LABEL_FONT_SIZE, width)


def _summary_lines(
    layout: PageLayout,
    depth: int,
    summary: str,
    has_right_column: bool,
) -> list[str]:
    x = layout.margin + depth * layout.indent_per_level + layout.indent_per_level
    width = _text_area_width(layout, x, has_right_column)
    return _wrap_text_to_width(summary, SUMMARY_FONT, SUMMARY_FONT_SIZE, width)


def _toc_row_layout(
    layout: PageLayout,
    depth: int,
    label: str,
    is_file: bool,
    right_column: str | None,
    summary: str | None,
    include_summaries: bool,
) -> tuple[list[str], list[str], int]:
    label_lines = _label_lines(layout, depth, label, is_file, right_column)
    has_right_column = right_column is not None
    summary_lines = (
        _summary_lines(layout, depth, summary, has_right_column)
        if include_summaries and is_file and summary
        else []
    )

    height = (
        layout.label_baseline_from_top
        + max(0, len(label_lines) - 1) * layout.label_line_height
    )
    if summary_lines:
        height += len(summary_lines) * layout.summary_line_height
    else:
        height = max(height, layout.row_height)
    height += layout.row_bottom_padding

    return label_lines, summary_lines, height


def _row_block_height(
    layout: PageLayout,
    depth: int,
    label: str,
    is_file: bool,
    right_column: str | None,
    summary: str | None,
    include_summaries: bool,
) -> int:
    _, _, height = _toc_row_layout(
        layout, depth, label, is_file, right_column, summary, include_summaries
    )
    return height


def _draw_page_background(
    c: canvas.Canvas,
    layout: PageLayout,
    background: tuple[float, float, float],
) -> None:
    c.setFillColor(colors.Color(*background))
    c.rect(0, 0, layout.width, layout.height, fill=1, stroke=0)
    c.setFillColor(colors.black)


def _row_stripe_color(background: tuple[float, float, float]) -> colors.Color:
    return colors.Color(*tint_with_black(background, ROW_STRIPE_BLACK_OPACITY))


def _draw_page_footer(
    c: canvas.Canvas,
    layout: PageLayout,
    page_number: int,
    *,
    include_summaries: bool,
) -> None:
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.black)
    if include_summaries:
        c.drawString(layout.margin, layout.margin, SUMMARY_DISCLAIMER)
    c.drawRightString(layout.width - layout.margin, layout.margin, str(page_number))


def _render_toc_pages(
    rows: list[tuple[int, str, bool, str | None, str | None]],
    include_summaries: bool,
    *,
    layout: PageLayout = DEFAULT_PAGE_LAYOUT,
    split: SplitContext | None = None,
    contents_background: tuple[float, float, float] = DEFAULT_BACKGROUND_RGB,
) -> PdfReader:
    buffer = io.BytesIO()
    page_count = 0
    row_index = 0
    y = layout.height - layout.margin

    def start_page(c: canvas.Canvas) -> float:
        nonlocal page_count, y
        page_count += 1
        _draw_page_background(c, layout, contents_background)
        y = layout.height - layout.margin
        if page_count == 1:
            c.setFont("Helvetica-Bold", 16)
            c.drawString(layout.margin, y, "Contents")
            y -= 28
            if split is not None and split.total_parts > 1:
                c.setFont("Helvetica", 11)
                notice = (
                    f"This archive is split into {split.total_parts} parts. "
                    f"This is part {split.part_number}."
                )
                for line in _wrap_text(notice, 80):
                    c.drawString(layout.margin, y, line)
                    y -= 14
                y -= 8
            return y
        return y

    def end_page(c: canvas.Canvas) -> None:
        _draw_page_footer(c, layout, page_count, include_summaries=include_summaries)

    c = canvas.Canvas(buffer, pagesize=layout.page_size.pagesize)
    y = start_page(c)

    for depth, label, is_file, right_column, summary in rows:
        block_height = _row_block_height(
            layout, depth, label, is_file, right_column, summary, include_summaries
        )
        if y - block_height < layout.content_bottom:
            end_page(c)
            c.showPage()
            y = start_page(c)

        row_top = y
        row_bottom = y - block_height

        if row_index % 2 == 1:
            c.setFillColor(_row_stripe_color(contents_background))
            c.rect(0, row_bottom, layout.width, block_height, fill=1, stroke=0)
            c.setFillColor(colors.black)

        x = layout.margin + depth * layout.indent_per_level
        label_lines, summary_lines, _ = _toc_row_layout(
            layout, depth, label, is_file, right_column, summary, include_summaries
        )
        label_baseline = row_top - layout.label_baseline_from_top
        c.setFont(LABEL_FONT, LABEL_FONT_SIZE)
        for line_index, line in enumerate(label_lines):
            c.drawString(
                x,
                label_baseline - line_index * layout.label_line_height,
                line,
            )
        if is_file and right_column is not None:
            c.drawRightString(
                layout.width - layout.margin, label_baseline, right_column
            )

        if summary_lines:
            last_label_baseline = label_baseline - (
                len(label_lines) - 1
            ) * layout.label_line_height
            summary_baseline = last_label_baseline - layout.summary_line_height
            c.setFont(SUMMARY_FONT, SUMMARY_FONT_SIZE)
            for line in summary_lines:
                c.drawString(x + layout.indent_per_level, summary_baseline, line)
                summary_baseline -= layout.summary_line_height

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
    *,
    layout: PageLayout = DEFAULT_PAGE_LAYOUT,
    cover_background: tuple[float, float, float] = DEFAULT_BACKGROUND_RGB,
) -> PdfReader:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=layout.page_size.pagesize)
    _draw_page_background(c, layout, cover_background)
    c.setFont("Helvetica-Bold", 14)
    y = layout.height - layout.margin
    for line in _wrap_text(relative_path, 60):
        c.drawString(layout.margin, y, line)
        y -= 18

    if include_summaries and summary:
        y -= 12
        c.setFont("Helvetica", 11)
        for line in _wrap_text(summary, 70):
            c.drawString(layout.margin, y, line)
            y -= 14

    c.setFont("Helvetica", 10)
    _draw_page_footer(c, layout, page_number, include_summaries=include_summaries)
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


def _first_document_size(
    part_documents: list[DocumentInfo],
    document_sizes: dict[str, PageSize],
) -> PageSize | None:
    if not part_documents:
        return None
    first = sorted(part_documents, key=lambda d: d.relative_path)[0]
    return document_sizes.get(first.relative_path)


def _build_pdf_bytes(
    part_documents: list[DocumentInfo],
    include_summaries: bool,
    *,
    all_documents: list[DocumentInfo] | None = None,
    split: SplitContext | None = None,
    contents_background: tuple[float, float, float] = DEFAULT_BACKGROUND_RGB,
    cover_background: tuple[float, float, float] = DEFAULT_BACKGROUND_RGB,
    page_size_options: PageSizeOptions | None = None,
) -> bytes:
    if not part_documents:
        raise PdfBuildError("No documents to concatenate")

    options = page_size_options or PageSizeOptions()
    toc_documents = all_documents or part_documents
    document_sizes = _document_target_sizes(toc_documents, options)
    first_document_size = _first_document_size(part_documents, document_sizes)
    index_page_size = _resolve_index_page_size(options, first_document_size)
    index_layout = _layout_for_page_size(index_page_size)

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
        toc_reader = _render_toc_pages(
            rows,
            include_summaries,
            layout=index_layout,
            split=split,
            contents_background=contents_background,
        )
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
    toc_reader = _render_toc_pages(
        rows,
        include_summaries,
        layout=index_layout,
        split=split,
        contents_background=contents_background,
    )

    writer = PdfWriter()
    for page in toc_reader.pages:
        writer.add_page(page)

    for doc in sorted(part_documents, key=lambda d: d.relative_path):
        cover_num = cover_pages[doc.relative_path]
        separator_size = _resolve_separator_page_size(
            options,
            document_sizes.get(doc.relative_path),
        )
        cover_layout = _layout_for_page_size(separator_size)
        cover_reader = _render_cover_page(
            doc.relative_path,
            doc.summary,
            cover_num,
            include_summaries,
            layout=cover_layout,
            cover_background=cover_background,
        )
        writer.add_page(cover_reader.pages[0])
        source = PdfReader(str(doc.path))
        for page in source.pages:
            writer.add_page(_snap_page_if_needed(page, options))

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
    contents_background: tuple[float, float, float] = DEFAULT_BACKGROUND_RGB,
    cover_background: tuple[float, float, float] = DEFAULT_BACKGROUND_RGB,
    page_size_options: PageSizeOptions | None = None,
) -> None:
    data = _build_pdf_bytes(
        documents,
        include_summaries,
        all_documents=all_documents,
        split=split,
        contents_background=contents_background,
        cover_background=cover_background,
        page_size_options=page_size_options,
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
    *,
    contents_background: tuple[float, float, float] = DEFAULT_BACKGROUND_RGB,
    cover_background: tuple[float, float, float] = DEFAULT_BACKGROUND_RGB,
    page_size_options: PageSizeOptions | None = None,
) -> int:
    part_documents = groups[part_number - 1]
    split = _split_context_for_groups(groups, all_documents, part_number)
    return len(
        _build_pdf_bytes(
            part_documents,
            include_summaries,
            all_documents=all_documents,
            split=split,
            contents_background=contents_background,
            cover_background=cover_background,
            page_size_options=page_size_options,
        )
    )
