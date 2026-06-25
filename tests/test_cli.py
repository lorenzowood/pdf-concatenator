from __future__ import annotations

import json
from pathlib import Path

import pytest
from pypdf import PdfReader

from pdf_concatenator.cli import main
from pdf_concatenator.sidecar import is_sidecar_valid, sidecar_path_for
from tests.helpers import make_pdf


@pytest.fixture
def doc_tree(tmp_path: Path) -> Path:
    root = tmp_path / "docs"
    make_pdf(root / "a.pdf", "Doc A")
    make_pdf(root / "b.pdf", "Doc B")
    return root


@pytest.fixture
def llm_config(tmp_path: Path) -> Path:
    config = tmp_path / "config"
    config.write_text(
        "LLM_API=open_ai\n"
        "LLM_SERVER=127.0.0.1:28911\n"
        "LLM_API_KEY=test-key\n"
        "LLM_MODEL=test-model\n"
        "LLM_PROMPT_TITLE_AND_SUMMARY=Summarise.\n"
    )
    return config


class TestConcatenateCli:
    def test_concatenates_without_summaries(self, doc_tree: Path, tmp_path: Path):
        output = tmp_path / "combined.pdf"
        code = main(["-o", str(output), str(doc_tree)])
        assert code == 0
        assert output.exists()
        assert len(PdfReader(str(output)).pages) > 0

    def test_no_pdfs_returns_error(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        code = main(["-o", str(tmp_path / "out.pdf"), str(empty)])
        assert code == 1

    def test_output_required_for_concatenation(self, doc_tree: Path):
        code = main([str(doc_tree)])
        assert code == 2

    def test_exclude_removes_files(self, doc_tree: Path, tmp_path: Path):
        output = tmp_path / "combined.pdf"
        code = main(
            [
                "-o",
                str(output),
                "--exclude",
                "b.pdf",
                str(doc_tree),
            ]
        )
        assert code == 0
        text = PdfReader(str(output)).pages[0].extract_text() or ""
        assert "a.pdf" in text
        assert "b.pdf" not in text

    def test_corrupt_pdf_aborts_without_output(
        self, doc_tree: Path, tmp_path: Path
    ):
        (doc_tree / "bad.pdf").write_bytes(b"not-a-pdf")
        output = tmp_path / "combined.pdf"
        code = main(["-o", str(output), str(doc_tree)])
        assert code == 1
        assert not output.exists()

    def test_include_summaries_uses_existing_sidecar(
        self, doc_tree: Path, tmp_path: Path, llm_config: Path, mocker
    ):
        pdf = doc_tree / "a.pdf"
        sidecar_path = sidecar_path_for(pdf)
        from pdf_concatenator.sidecar import sha256_file

        sidecar_path.write_text(
            json.dumps(
                {
                    "filename": "a.pdf",
                    "sha256": sha256_file(pdf),
                    "title": "Cached Title",
                    "summary": "Cached summary.",
                    "generated-by": "cached",
                    "generated-on": "2026-01-01T00:00:00+00:00",
                }
            )
        )
        mock_llm = mocker.patch("pdf_concatenator.summaries.generate_title_and_summary")
        output = tmp_path / "combined.pdf"
        code = main(
            [
                "-o",
                str(output),
                "--include-summaries",
                "--config",
                str(llm_config),
                "--exclude",
                "b.pdf",
                str(doc_tree),
            ]
        )
        assert code == 0
        mock_llm.assert_not_called()
        text = PdfReader(str(output)).pages[0].extract_text() or ""
        assert "Cached summary." in text

    def test_include_summaries_calls_llm_when_sidecar_missing(
        self, doc_tree: Path, tmp_path: Path, llm_config: Path, mocker
    ):
        from pdf_concatenator.llm import TitleAndSummary

        mocker.patch(
            "pdf_concatenator.summaries.generate_title_and_summary",
            return_value=TitleAndSummary(title="Generated", summary="Fresh summary."),
        )
        output = tmp_path / "combined.pdf"
        code = main(
            [
                "-o",
                str(output),
                "--include-summaries",
                "--config",
                str(llm_config),
                "--exclude",
                "b.pdf",
                str(doc_tree),
            ]
        )
        assert code == 0
        assert is_sidecar_valid(doc_tree / "a.pdf")
        text = PdfReader(str(output)).pages[0].extract_text() or ""
        assert "Fresh summary." in text

    def test_missing_config_fails_when_summaries_required(
        self, doc_tree: Path, tmp_path: Path
    ):
        output = tmp_path / "combined.pdf"
        code = main(
            [
                "-o",
                str(output),
                "--include-summaries",
                "--config",
                str(tmp_path / "missing-config"),
                str(doc_tree),
            ]
        )
        assert code == 1
        assert not output.exists()


class TestRegenerateSummariesCli:
    def test_regenerate_only_updates_sidecars(
        self, doc_tree: Path, tmp_path: Path, llm_config: Path, mocker
    ):
        from pdf_concatenator.llm import TitleAndSummary

        mocker.patch(
            "pdf_concatenator.summaries.generate_title_and_summary",
            return_value=TitleAndSummary(title="T", summary="S"),
        )
        code = main(
            [
                "--regenerate-summaries",
                "--config",
                str(llm_config),
                "--exclude",
                "b.pdf",
                str(doc_tree),
            ]
        )
        assert code == 0
        assert is_sidecar_valid(doc_tree / "a.pdf")
        assert not sidecar_path_for(doc_tree / "b.pdf").exists()

    def test_regenerate_rejects_output_flag(self, doc_tree: Path, llm_config: Path):
        code = main(
            [
                "--regenerate-summaries",
                "-o",
                "out.pdf",
                "--config",
                str(llm_config),
                str(doc_tree),
            ]
        )
        assert code == 2

    def test_llm_failure_returns_error(
        self, doc_tree: Path, llm_config: Path, mocker
    ):
        from pdf_concatenator.llm import LlmError

        mocker.patch(
            "pdf_concatenator.summaries.generate_title_and_summary",
            side_effect=LlmError("LLM request failed"),
        )
        code = main(
            [
                "--regenerate-summaries",
                "--config",
                str(llm_config),
                "--exclude",
                "b.pdf",
                str(doc_tree),
            ]
        )
        assert code == 1
