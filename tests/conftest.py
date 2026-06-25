from __future__ import annotations

from pathlib import Path

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def make_pdf(path: Path, title: str = "Test") -> Path:
    """Create a minimal single-page PDF at path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setTitle(title)
    c.drawString(72, 720, title)
    c.showPage()
    c.save()
    return path


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
