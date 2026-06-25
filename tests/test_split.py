from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader

from pdf_concatenator.pdf_build import DocumentInfo, PdfBuildError
from pdf_concatenator.split import build_split_outputs, part_output_paths
from tests.helpers import make_pdf


class TestPartOutputPaths:
    def test_single_part_uses_original_path(self, tmp_path: Path):
        base = tmp_path / "submission.pdf"
        assert part_output_paths(base, 1) == [base]

    def test_multiple_parts_add_suffix(self, tmp_path: Path):
        base = tmp_path / "submission.pdf"
        paths = part_output_paths(base, 3)
        assert paths == [
            tmp_path / "submission_part_1.pdf",
            tmp_path / "submission_part_2.pdf",
            tmp_path / "submission_part_3.pdf",
        ]


class TestBuildSplitOutputs:
    def test_splits_when_over_limit(self, tmp_path: Path):
        root = tmp_path / "docs"
        docs = [
            DocumentInfo(
                path=make_pdf(root / f"doc{i}.pdf", f"Doc {i}"),
                relative_path=f"doc{i}.pdf",
                title=f"Doc {i}",
                summary=None,
            )
            for i in range(4)
        ]
        output = tmp_path / "bundle.pdf"
        # Small limit forces multiple parts
        paths = build_split_outputs(
            docs,
            output,
            include_summaries=False,
            max_bytes=4_000,
        )
        assert len(paths) >= 2
        for path in paths:
            assert path.exists()
            assert path.stat().st_size <= 8_000
        assert all("_part_" in p.name for p in paths)

    def test_single_output_when_under_limit(self, tmp_path: Path):
        root = tmp_path / "docs"
        docs = [
            DocumentInfo(
                path=make_pdf(root / "a.pdf", "A"),
                relative_path="a.pdf",
                title="A",
                summary=None,
            )
        ]
        output = tmp_path / "bundle.pdf"
        paths = build_split_outputs(
            docs,
            output,
            include_summaries=False,
            max_bytes=50 * 1024 * 1024,
        )
        assert paths == [output]
        assert output.exists()

    def test_toc_lists_all_docs_and_marks_parts(self, tmp_path: Path):
        root = tmp_path / "docs"
        docs = [
            DocumentInfo(
                path=make_pdf(root / f"doc{i}.pdf", f"Doc {i}"),
                relative_path=f"doc{i}.pdf",
                title=f"Doc {i}",
                summary=None,
            )
            for i in range(4)
        ]
        output = tmp_path / "bundle.pdf"
        paths = build_split_outputs(
            docs,
            output,
            include_summaries=False,
            max_bytes=4_000,
        )
        part1_text = PdfReader(str(paths[0])).pages[0].extract_text() or ""
        assert "split into" in part1_text
        assert "part 1" in part1_text.lower()
        assert "doc0.pdf" in part1_text
        assert "doc3.pdf" in part1_text
        assert "Part 2" in part1_text or "part 2" in part1_text.lower()

    def test_raises_when_single_doc_exceeds_limit(self, tmp_path: Path):
        root = tmp_path / "docs"
        docs = [
            DocumentInfo(
                path=make_pdf(root / "big.pdf", "Big"),
                relative_path="big.pdf",
                title="Big",
                summary=None,
            )
        ]
        with pytest.raises(PdfBuildError, match="exceeds"):
            build_split_outputs(
                docs,
                tmp_path / "bundle.pdf",
                include_summaries=False,
                max_bytes=500,
            )
