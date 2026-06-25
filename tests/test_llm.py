from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest
from pypdf import PdfWriter

from pdf_concatenator.config import LlmConfig
from pdf_concatenator.llm import LlmError, generate_title_and_summary


def _make_config() -> LlmConfig:
    return LlmConfig(
        api="open_ai",
        server="127.0.0.1:28911",
        api_key="test-key",
        model="test-model",
        prompt="Summarise this PDF.",
    )


def _minimal_pdf(path: Path) -> Path:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_metadata({"/Title": "Meta Title"})
    with path.open("wb") as f:
        writer.write(f)
    return path


class TestGenerateTitleAndSummary:
    def test_sends_pdf_to_openai_compatible_endpoint(self, tmp_path: Path, mocker):
        pdf = _minimal_pdf(tmp_path / "doc.pdf")
        pdf_bytes = pdf.read_bytes()
        b64 = base64.standard_b64encode(pdf_bytes).decode("ascii")

        mock_response = mocker.Mock()
        mock_response.raise_for_status = mocker.Mock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "title": "Document Title",
                                "summary": "A short summary.",
                            }
                        )
                    }
                }
            ]
        }
        mock_post = mocker.patch(
            "pdf_concatenator.llm.httpx.post", return_value=mock_response
        )

        result = generate_title_and_summary(_make_config(), pdf)
        assert result.title == "Document Title"
        assert result.summary == "A short summary."

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[0][0] == "http://127.0.0.1:28911/v1/chat/completions"
        assert call_kwargs[1]["headers"]["Authorization"] == "Bearer test-key"
        body = call_kwargs[1]["json"]
        assert body["model"] == "test-model"
        user_content = body["messages"][1]["content"]
        assert any(
            b64 in (part.get("file", {}).get("file_data", "") or "")
            for part in user_content
            if isinstance(part, dict)
        )

    def test_includes_metadata_in_request(self, tmp_path: Path, mocker):
        pdf = _minimal_pdf(tmp_path / "doc.pdf")
        mock_response = mocker.Mock()
        mock_response.raise_for_status = mocker.Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"title": "T", "summary": "S"}'}}]
        }
        mock_post = mocker.patch(
            "pdf_concatenator.llm.httpx.post", return_value=mock_response
        )
        generate_title_and_summary(_make_config(), pdf)
        body = mock_post.call_args[1]["json"]
        user_content = body["messages"][1]["content"]
        text_parts = [
            part.get("text", "")
            for part in user_content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        assert any("Meta Title" in t for t in text_parts)

    def test_raises_on_http_error(self, tmp_path: Path, mocker):
        pdf = _minimal_pdf(tmp_path / "doc.pdf")
        mock_response = mocker.Mock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=mocker.Mock(), response=mocker.Mock()
        )
        mocker.patch("pdf_concatenator.llm.httpx.post", return_value=mock_response)
        with pytest.raises(LlmError, match="LLM request failed"):
            generate_title_and_summary(_make_config(), pdf)

    def test_raises_on_invalid_json_response(self, tmp_path: Path, mocker):
        pdf = _minimal_pdf(tmp_path / "doc.pdf")
        mock_response = mocker.Mock()
        mock_response.raise_for_status = mocker.Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "not json"}}]
        }
        mocker.patch("pdf_concatenator.llm.httpx.post", return_value=mock_response)
        with pytest.raises(LlmError, match="parse"):
            generate_title_and_summary(_make_config(), pdf)

    def test_raises_on_missing_fields(self, tmp_path: Path, mocker):
        pdf = _minimal_pdf(tmp_path / "doc.pdf")
        mock_response = mocker.Mock()
        mock_response.raise_for_status = mocker.Mock()
        mock_response.json.return_value = {
            "choices": [
                {"message": {"content": json.dumps({"title": "only title"})}}
            ]
        }
        mocker.patch("pdf_concatenator.llm.httpx.post", return_value=mock_response)
        with pytest.raises(LlmError, match="title"):
            generate_title_and_summary(_make_config(), pdf)

    def test_raises_on_summary_over_100_words(self, tmp_path: Path, mocker):
        pdf = _minimal_pdf(tmp_path / "doc.pdf")
        long_summary = " ".join(["word"] * 101)
        mock_response = mocker.Mock()
        mock_response.raise_for_status = mocker.Mock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"title": "T", "summary": long_summary}
                        )
                    }
                }
            ]
        }
        mocker.patch("pdf_concatenator.llm.httpx.post", return_value=mock_response)
        with pytest.raises(LlmError, match="100 words"):
            generate_title_and_summary(_make_config(), pdf)
