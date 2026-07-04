from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4, elevenSeventeen, letter
from reportlab.pdfgen import canvas

from pdf_concatenator.page_size import (
    PageSize,
    closest_page_size,
    effective_page_size,
    parse_page_size,
    parse_page_size_list,
    snap_page_to_size,
    PageSizeParseError,
)
from pdf_concatenator.page_size_options import resolve_page_size_options
from pdf_concatenator.pdf_build import (
    DocumentInfo,
    PageSizeOptions,
    build_concatenated_pdf,
)
from tests.helpers import make_pdf


def _make_sized_pdf(path: Path, pagesize: tuple[float, float], label: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=pagesize)
    c.drawString(72, pagesize[1] - 72, label)
    c.showPage()
    c.save()
    return path


class TestParsePageSize:
    def test_parses_known_sizes(self):
        assert parse_page_size("a4").name == "a4"
        assert parse_page_size("Letter").name == "letter"
        assert parse_page_size("ledger").name == "ledger"

    def test_rejects_unknown_size(self):
        with pytest.raises(PageSizeParseError, match="Unknown page size"):
            parse_page_size("b2")

    def test_parse_page_size_list(self):
        sizes = parse_page_size_list("a4, a3")
        assert [size.name for size in sizes] == ["a4", "a3"]


class TestClosestPageSize:
    def test_letter_snaps_to_a4_when_only_a4_allowed(self):
        width, height = letter
        result = closest_page_size(width, height, (parse_page_size("a4"),))
        assert result.name == "a4"
        assert result.width == pytest.approx(A4[0])
        assert result.height == pytest.approx(A4[1])

    def test_tabloid_snaps_to_a3_when_a4_and_a3_allowed(self):
        width, height = elevenSeventeen
        result = closest_page_size(
            width,
            height,
            parse_page_size_list("a4,a3"),
        )
        assert result.name == "a3"

    def test_landscape_source_prefers_landscape_orientation(self):
        width, height = letter[1], letter[0]
        result = closest_page_size(width, height, (parse_page_size("a4"),))
        assert result.width > result.height


class TestSnapPageToSize:
    def test_snapped_page_has_target_dimensions(self, tmp_path: Path):
        source = _make_sized_pdf(tmp_path / "letter.pdf", letter, "Letter")
        reader = PdfReader(str(source))
        target = parse_page_size("a4")
        snapped = snap_page_to_size(reader.pages[0], target)
        assert float(snapped.mediabox.width) == pytest.approx(target.width)
        assert float(snapped.mediabox.height) == pytest.approx(target.height)


class TestResolvePageSizeOptions:
    def test_cli_overrides_config(self, tmp_path: Path):
        config = tmp_path / "config"
        config.write_text("PAGE_SIZES=a3\nINDEX_PAGE_SIZE=a3\n")
        options, error = resolve_page_size_options(
            config_path=config,
            page_sizes="a4",
            index_page_size=None,
            separator_page_size=None,
        )
        assert error is None
        assert options is not None
        assert options.allowed_sizes == (parse_page_size("a4"),)
        assert options.index_page_size == parse_page_size("a3")

    def test_reads_defaults_from_config(self, tmp_path: Path):
        config = tmp_path / "config"
        config.write_text("SEPARATOR_PAGE_SIZE=a3\n")
        options, error = resolve_page_size_options(
            config_path=config,
            page_sizes=None,
            index_page_size=None,
            separator_page_size=None,
        )
        assert error is None
        assert options is not None
        assert options.separator_page_size == parse_page_size("a3")


class TestBuildWithPageSizes:
    def test_default_generated_pages_use_a4(self, tmp_path: Path):
        root = tmp_path / "docs"
        letter_pdf = _make_sized_pdf(root / "letter.pdf", letter, "Letter doc")
        output = tmp_path / "out.pdf"
        build_concatenated_pdf(
            [
                DocumentInfo(
                    path=letter_pdf,
                    relative_path="letter.pdf",
                    title="Letter",
                    summary=None,
                )
            ],
            output,
            include_summaries=False,
        )
        reader = PdfReader(str(output))
        toc_page = reader.pages[0]
        cover_page = reader.pages[1]
        assert float(toc_page.mediabox.width) == pytest.approx(A4[0], rel=1e-3)
        assert float(cover_page.mediabox.width) == pytest.approx(A4[0], rel=1e-3)
        assert float(reader.pages[2].mediabox.width) == pytest.approx(letter[0], rel=1e-3)

    def test_page_sizes_snaps_source_and_matches_separator(self, tmp_path: Path):
        root = tmp_path / "docs"
        letter_pdf = _make_sized_pdf(root / "letter.pdf", letter, "Letter doc")
        output = tmp_path / "out.pdf"
        build_concatenated_pdf(
            [
                DocumentInfo(
                    path=letter_pdf,
                    relative_path="letter.pdf",
                    title="Letter",
                    summary=None,
                )
            ],
            output,
            include_summaries=False,
            page_size_options=PageSizeOptions(allowed_sizes=(parse_page_size("a4"),)),
        )
        reader = PdfReader(str(output))
        for page in reader.pages:
            assert float(page.mediabox.width) == pytest.approx(A4[0], rel=1e-3)
            assert float(page.mediabox.height) == pytest.approx(A4[1], rel=1e-3)

    def test_separator_follows_snapped_document_size(self, tmp_path: Path):
        root = tmp_path / "docs"
        tabloid_pdf = _make_sized_pdf(root / "a-wide.pdf", elevenSeventeen, "Tabloid doc")
        a4_pdf = make_pdf(root / "b-narrow.pdf", "A4 doc")
        output = tmp_path / "out.pdf"
        allowed = parse_page_size_list("a4,a3")
        build_concatenated_pdf(
            [
                DocumentInfo(
                    path=tabloid_pdf,
                    relative_path="a-wide.pdf",
                    title="Wide",
                    summary=None,
                ),
                DocumentInfo(
                    path=a4_pdf,
                    relative_path="b-narrow.pdf",
                    title="Narrow",
                    summary=None,
                ),
            ],
            output,
            include_summaries=False,
            page_size_options=PageSizeOptions(allowed_sizes=allowed),
        )
        reader = PdfReader(str(output))
        a3 = parse_page_size("a3")
        assert float(reader.pages[0].mediabox.width) == pytest.approx(a3.width, rel=1e-3)
        assert float(reader.pages[1].mediabox.width) == pytest.approx(a3.width, rel=1e-3)
        assert float(reader.pages[2].mediabox.width) == pytest.approx(a3.width, rel=1e-3)
        assert float(reader.pages[3].mediabox.width) == pytest.approx(A4[0], rel=1e-3)
        assert float(reader.pages[4].mediabox.width) == pytest.approx(A4[0], rel=1e-3)
