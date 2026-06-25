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
