from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import make_pdf


@pytest.fixture
def sample_tree(tmp_path: Path) -> Path:
    """Build a small directory tree with PDFs and non-PDF files."""
    root = tmp_path / "docs"
    make_pdf(root / "summary.pdf", "Summary")
    make_pdf(root / "reports" / "2024" / "jan.pdf", "January")
    make_pdf(root / "reports" / "2024" / "feb.pdf", "February")
    make_pdf(root / "reports" / "2023" / "annual.pdf", "Annual")
    (root / "readme.txt").write_text("not a pdf")
    (root / "reports" / "notes.md").write_text("also not a pdf")
    return root
