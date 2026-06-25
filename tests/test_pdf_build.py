from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from pypdf import PdfReader

from pdf_concatenator.pdf_build import DocumentInfo, build_concatenated_pdf
from tests.helpers import make_pdf


@dataclass
class TreeFixture:
    root: Path
    docs: list[DocumentInfo]


@pytest.fixture
def two_doc_tree(tmp_path: Path) -> TreeFixture:
    root = tmp_path / "docs"
    jan = make_pdf(root / "reports" / "2024" / "jan.pdf", "January")
    summary = make_pdf(root / "summary.pdf", "Summary")
    return TreeFixture(
        root=root,
        docs=[
            DocumentInfo(
                path=jan,
                relative_path="reports/2024/jan.pdf",
                title="January Report",
                summary=None,
            ),
            DocumentInfo(
                path=summary,
                relative_path="summary.pdf",
                title="Summary",
                summary=None,
            ),
        ],
    )


class TestBuildConcatenatedPdf:
    def test_output_page_count_includes_toc_covers_and_sources(
        self, two_doc_tree: TreeFixture, tmp_path: Path
    ):
        output = tmp_path / "out.pdf"
        build_concatenated_pdf(two_doc_tree.docs, output, include_summaries=False)
        reader = PdfReader(str(output))
        # 1 TOC + (1 cover + 1 source) * 2 docs = 5 pages
        assert len(reader.pages) == 5

    def test_cover_page_contains_relative_path(
        self, two_doc_tree: TreeFixture, tmp_path: Path
    ):
        output = tmp_path / "out.pdf"
        build_concatenated_pdf(two_doc_tree.docs, output, include_summaries=False)
        reader = PdfReader(str(output))
        # Page 2 is first cover (after 1-page TOC)
        text = reader.pages[1].extract_text() or ""
        assert "reports/2024/jan.pdf" in text

    def test_cover_includes_summary_when_requested(
        self, two_doc_tree: TreeFixture, tmp_path: Path
    ):
        docs = [
            DocumentInfo(
                path=two_doc_tree.docs[0].path,
                relative_path=two_doc_tree.docs[0].relative_path,
                title="January Report",
                summary="A concise January summary.",
            ),
            two_doc_tree.docs[1],
        ]
        output = tmp_path / "out.pdf"
        build_concatenated_pdf(docs, output, include_summaries=True)
        reader = PdfReader(str(output))
        text = reader.pages[1].extract_text() or ""
        assert "A concise January summary." in text

    def test_toc_lists_folders_and_files_with_page_numbers(
        self, two_doc_tree: TreeFixture, tmp_path: Path
    ):
        output = tmp_path / "out.pdf"
        build_concatenated_pdf(two_doc_tree.docs, output, include_summaries=False)
        reader = PdfReader(str(output))
        toc_text = reader.pages[0].extract_text() or ""
        assert "reports" in toc_text
        assert "jan.pdf" in toc_text
        assert "summary.pdf" in toc_text
        # First cover page is page 2
        assert "2" in toc_text

    def test_toc_includes_summary_when_requested(
        self, two_doc_tree: TreeFixture, tmp_path: Path
    ):
        docs = [
            DocumentInfo(
                path=two_doc_tree.docs[0].path,
                relative_path=two_doc_tree.docs[0].relative_path,
                title="January Report",
                summary="January blurb.",
            ),
            two_doc_tree.docs[1],
        ]
        output = tmp_path / "out.pdf"
        build_concatenated_pdf(docs, output, include_summaries=True)
        reader = PdfReader(str(output))
        toc_text = reader.pages[0].extract_text() or ""
        assert "January blurb." in toc_text

    def test_cover_page_number_at_bottom_matches_position(
        self, two_doc_tree: TreeFixture, tmp_path: Path
    ):
        output = tmp_path / "out.pdf"
        build_concatenated_pdf(two_doc_tree.docs, output, include_summaries=False)
        reader = PdfReader(str(output))
        # Order: jan (reports/...) then summary.pdf. Second cover is page 4.
        text = reader.pages[3].extract_text() or ""
        assert "4" in text
        assert "summary.pdf" in text

    def test_raises_on_corrupt_pdf(self, tmp_path: Path):
        bad = tmp_path / "bad.pdf"
        bad.write_bytes(b"not a pdf")
        docs = [
            DocumentInfo(
                path=bad,
                relative_path="bad.pdf",
                title="Bad",
                summary=None,
            )
        ]
        with pytest.raises(Exception):
            build_concatenated_pdf(docs, tmp_path / "out.pdf", include_summaries=False)

    def test_toc_pages_have_footer_page_numbers(self, mocker):
        from pdf_concatenator.pdf_build import MARGIN, _render_toc_pages

        rows = [(0, f"f{i}.pdf", True, str(i + 2), None) for i in range(4)]
        footer_calls: list[str] = []
        original_canvas = __import__(
            "reportlab.pdfgen.canvas", fromlist=["Canvas"]
        ).Canvas

        class CapturingCanvas(original_canvas):
            def drawRightString(self, x, y, text, **kwargs):
                if y == MARGIN:
                    footer_calls.append(text)
                return super().drawRightString(x, y, text, **kwargs)

        mocker.patch("pdf_concatenator.pdf_build.canvas.Canvas", CapturingCanvas)
        _render_toc_pages(rows, include_summaries=False)

        assert footer_calls == ["1"]

    def test_multipage_toc_has_numbered_footers(self, mocker):
        from pdf_concatenator.pdf_build import MARGIN, _render_toc_pages

        rows = [(0, f"f{i}.pdf", True, str(i + 10), None) for i in range(50)]
        footer_calls: list[str] = []
        original_canvas = __import__(
            "reportlab.pdfgen.canvas", fromlist=["Canvas"]
        ).Canvas

        class CapturingCanvas(original_canvas):
            def drawRightString(self, x, y, text, **kwargs):
                if y == MARGIN:
                    footer_calls.append(text)
                return super().drawRightString(x, y, text, **kwargs)

        mocker.patch("pdf_concatenator.pdf_build.canvas.Canvas", CapturingCanvas)
        reader = _render_toc_pages(rows, include_summaries=False)

        assert len(reader.pages) >= 2
        assert footer_calls == [str(i) for i in range(1, len(reader.pages) + 1)]

    def test_toc_row_backgrounds_tile_without_gaps(self, mocker):
        from pdf_concatenator.pdf_build import (
            MARGIN,
            PAGE_HEIGHT,
            ROW_HEIGHT,
            _render_toc_pages,
        )

        rows = [(0, f"f{i}.pdf", True, str(i + 2), None) for i in range(4)]
        rect_calls: list[tuple[float, float, float, float]] = []
        original_canvas = __import__(
            "reportlab.pdfgen.canvas", fromlist=["Canvas"]
        ).Canvas

        class CapturingCanvas(original_canvas):
            def rect(self, x, y, width, height, **kwargs):
                rect_calls.append((x, y, width, height))
                return super().rect(x, y, width, height, **kwargs)

        mocker.patch("pdf_concatenator.pdf_build.canvas.Canvas", CapturingCanvas)
        _render_toc_pages(rows, include_summaries=False)

        first_row_top = PAGE_HEIGHT - MARGIN - 28
        first_row_bottom = first_row_top - ROW_HEIGHT

        assert len(rect_calls) == 2
        assert rect_calls[0][1] == pytest.approx(first_row_bottom - ROW_HEIGHT)
        assert rect_calls[0][3] == ROW_HEIGHT
        assert rect_calls[1][1] == pytest.approx(first_row_bottom - 3 * ROW_HEIGHT)
        assert rect_calls[1][3] == ROW_HEIGHT

    def test_summary_disclaimer_on_toc_and_cover_when_including_summaries(
        self, two_doc_tree: TreeFixture, tmp_path: Path
    ):
        docs = [
            DocumentInfo(
                path=two_doc_tree.docs[0].path,
                relative_path=two_doc_tree.docs[0].relative_path,
                title="January Report",
                summary="January blurb.",
            ),
            two_doc_tree.docs[1],
        ]
        output = tmp_path / "out.pdf"
        build_concatenated_pdf(docs, output, include_summaries=True)
        reader = PdfReader(str(output))
        disclaimer = "Summaries are generated automatically"
        assert disclaimer in (reader.pages[0].extract_text() or "")
        assert disclaimer in (reader.pages[1].extract_text() or "")

    def test_no_summary_disclaimer_without_summaries(
        self, two_doc_tree: TreeFixture, tmp_path: Path
    ):
        output = tmp_path / "out.pdf"
        build_concatenated_pdf(two_doc_tree.docs, output, include_summaries=False)
        reader = PdfReader(str(output))
        full_text = "".join(page.extract_text() or "" for page in reader.pages)
        assert "generated automatically" not in full_text

    def test_toc_wraps_long_filename_before_part_column(self, tmp_path: Path):
        from pdf_concatenator.pdf_build import (
            LABEL_FONT,
            LABEL_FONT_SIZE,
            RIGHT_COLUMN_RESERVE,
            PAGE_WIDTH,
            MARGIN,
            SplitContext,
            _label_lines,
            _render_toc_pages,
            _text_width,
        )

        long_name = (
            "2005-03-01 Estates & Management Ltd Scannable Document on "
            "May 22, 2020 at 14_08_03.pdf"
        )
        rows = [(0, long_name, True, "Part 2", "A short summary.")]
        lines = _label_lines(0, long_name, True, "Part 2")
        assert len(lines) > 1

        max_line_width = PAGE_WIDTH - MARGIN - RIGHT_COLUMN_RESERVE - MARGIN
        for line in lines:
            assert _text_width(LABEL_FONT, LABEL_FONT_SIZE, line) <= max_line_width + 1

        reader = _render_toc_pages(
            rows,
            include_summaries=True,
            split=SplitContext(1, 2, {long_name: 2}),
        )
        toc_text = reader.pages[0].extract_text() or ""
        assert "Part 2" in toc_text
        assert "14_08_03.pdf" in toc_text
