from __future__ import annotations

from pathlib import Path

import pytest

from pdf_concatenator.frontmatter import (
    FrontMatterExpressionError,
    compile_expression,
    load_front_matter_for,
    parse_front_matter,
)


class TestParseFrontMatter:
    def test_fenced_markdown(self):
        text = (
            "---\n"
            "company: Acunu\n"
            'original_headline: "Hall of Fame news: Acunu"\n'
            "people: [Andy Harter, Andy Hopper]\n"
            "---\n\nbody text\n"
        )
        fm = parse_front_matter(text)
        assert fm["company"] == "Acunu"
        assert fm["original_headline"] == "Hall of Fame news: Acunu"
        assert fm["people"] == ["Andy Harter", "Andy Hopper"]

    def test_bare_block(self):
        fm = parse_front_matter("section: news\nsummary: hi\n")
        assert fm == {"section": "news", "summary": "hi"}

    def test_escaped_quotes_in_value(self):
        fm = parse_front_matter('---\nt: "a \\"b\\" c"\n---\n')
        assert fm["t"] == 'a "b" c'

    def test_empty_list(self):
        assert parse_front_matter("people: []\n")["people"] == []


class TestExpressionEvaluation:
    FIELDS = {
        "original_headline": "RealVNC — Conquering the world",
        "section": "interview",
        "summary": "Andy Harter discusses the move into automotive.",
        "people": ["Andy Harter", "Andy Hopper"],
        "company": "RealVNC",
    }

    def _eval(self, expr: str, fields=None) -> str:
        return compile_expression(expr).evaluate(fields or self.FIELDS)

    def test_plain_field(self):
        assert self._eval("summary") == "Andy Harter discusses the move into automotive."

    def test_missing_field_is_empty(self):
        assert self._eval("nonexistent") == ""

    def test_string_literal_concat(self):
        assert self._eval('company " / " section') == "RealVNC / interview"

    def test_escaped_characters(self):
        assert self._eval(r"summary \(section\)") == (
            "Andy Harter discusses the move into automotive.(interview)"
        )

    def test_ternary_true_branch(self):
        assert self._eval('original_headline ? "has headline" : "none"') == "has headline"

    def test_ternary_false_branch(self):
        assert self._eval('missing ? "yes" : "no"') == "no"

    def test_ternary_optional_else_defaults_empty(self):
        assert self._eval('missing ? "prefix: "') == ""

    def test_parenthesised_ternary_then_trailing_terms(self):
        result = self._eval(
            '(original_headline ? original_headline ": ") summary " (" section ")"'
        )
        assert result == (
            "RealVNC — Conquering the world: "
            "Andy Harter discusses the move into automotive. (interview)"
        )

    def test_same_expression_without_headline(self):
        fields = {"summary": "Grown to 15 staff.", "section": "news"}
        result = compile_expression(
            '(original_headline ? original_headline ": ") summary " (" section ")"'
        ).evaluate(fields)
        assert result == "Grown to 15 staff. (news)"

    def test_list_stringifies_comma_separated(self):
        assert self._eval("people") == "Andy Harter, Andy Hopper"

    @pytest.mark.parametrize("bad", ['"unterminated', "summary )", "(summary", "", "?"])
    def test_malformed_expressions_raise(self, bad):
        with pytest.raises(FrontMatterExpressionError):
            compile_expression(bad)


class TestCompanionLookup:
    def test_finds_md_beside_pdf(self, tmp_path: Path):
        (tmp_path / "doc.pdf").write_bytes(b"%PDF-1.4")
        (tmp_path / "doc.md").write_text("---\nsummary: from md\n---\n")
        fm = load_front_matter_for(tmp_path / "doc.pdf")
        assert fm == {"summary": "from md"}

    def test_finds_in_explicit_dir(self, tmp_path: Path):
        pdf_dir = tmp_path / "pdfs"
        md_dir = tmp_path / "src"
        pdf_dir.mkdir()
        md_dir.mkdir()
        (pdf_dir / "doc.pdf").write_bytes(b"%PDF-1.4")
        (md_dir / "doc.md").write_text("summary: elsewhere\n")
        fm = load_front_matter_for(pdf_dir / "doc.pdf", md_dir)
        assert fm == {"summary": "elsewhere"}

    def test_missing_returns_none(self, tmp_path: Path):
        (tmp_path / "doc.pdf").write_bytes(b"%PDF-1.4")
        assert load_front_matter_for(tmp_path / "doc.pdf") is None
