from __future__ import annotations

import pytest

from pdf_concatenator.pdf_build import DocumentInfo
from pdf_concatenator.size_estimate import estimate_part_bytes, estimate_total_parts
from tests.helpers import make_pdf


class TestEstimatePartBytes:
    def test_larger_parts_estimate_larger(self, tmp_path):
        root = tmp_path / "docs"
        docs = [
            DocumentInfo(
                path=make_pdf(root / f"doc{i}.pdf", f"Doc {i}"),
                relative_path=f"doc{i}.pdf",
                title=f"Doc {i}",
                summary=None,
            )
            for i in range(3)
        ]
        one = estimate_part_bytes([docs[0]], docs, False, total_parts=1)
        three = estimate_part_bytes(docs, docs, False, total_parts=1)
        assert three > one

    def test_split_notice_adds_overhead(self, tmp_path):
        root = tmp_path / "docs"
        docs = [
            DocumentInfo(
                path=make_pdf(root / "a.pdf", "A"),
                relative_path="a.pdf",
                title="A",
                summary=None,
            )
        ]
        single = estimate_part_bytes(docs, docs, False, total_parts=1)
        split = estimate_part_bytes(docs, docs, False, total_parts=2)
        assert split > single


class TestEstimateTotalParts:
    def test_unassigned_documents_imply_future_part(self, tmp_path):
        root = tmp_path / "docs"
        docs = [
            DocumentInfo(
                path=make_pdf(root / f"doc{i}.pdf", f"D{i}"),
                relative_path=f"doc{i}.pdf",
                title=f"D{i}",
                summary=None,
            )
            for i in range(3)
        ]
        assert estimate_total_parts([docs[:1]], docs) == 2
