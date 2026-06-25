from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path

import httpx
from pypdf import PdfReader

from pdf_concatenator.config import LlmConfig


class LlmError(Exception):
    pass


@dataclass(frozen=True)
class TitleAndSummary:
    title: str
    summary: str


def _extract_metadata(pdf_path: Path) -> dict[str, str]:
    reader = PdfReader(str(pdf_path))
    metadata = reader.metadata or {}
    result: dict[str, str] = {}
    for key, value in metadata.items():
        if value is not None:
            name = key.lstrip("/")
            result[name] = str(value)
    return result


def _parse_llm_content(content: str) -> TitleAndSummary:
    content = content.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if fence_match:
        content = fence_match.group(1)
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LlmError(f"Failed to parse LLM response as JSON: {exc}") from exc

    title = data.get("title")
    summary = data.get("summary")
    if not title or not summary:
        raise LlmError("LLM response missing title or summary fields")

    word_count = len(summary.split())
    if word_count > 100:
        raise LlmError(f"Summary exceeds 100 words ({word_count})")

    return TitleAndSummary(title=str(title).strip(), summary=str(summary).strip())


def _build_messages(config: LlmConfig, pdf_path: Path) -> list[dict]:
    metadata = _extract_metadata(pdf_path)
    pdf_bytes = pdf_path.read_bytes()
    b64 = base64.standard_b64encode(pdf_bytes).decode("ascii")
    metadata_lines = "\n".join(f"{k}: {v}" for k, v in sorted(metadata.items()))
    text = (
        f"Filename: {pdf_path.name}\n"
        f"Metadata:\n{metadata_lines or '(none)'}"
    )
    return [
        {"role": "system", "content": config.prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": text},
                {
                    "type": "file",
                    "file": {
                        "filename": pdf_path.name,
                        "file_data": f"data:application/pdf;base64,{b64}",
                    },
                },
            ],
        },
    ]


def generate_title_and_summary(config: LlmConfig, pdf_path: Path) -> TitleAndSummary:
    if config.api != "open_ai":
        raise LlmError(f"Unsupported LLM_API value: {config.api}")

    url = f"http://{config.server}/v1/chat/completions"
    payload = {
        "model": config.model,
        "messages": _build_messages(config, pdf_path),
    }
    headers = {"Authorization": f"Bearer {config.api_key}"}

    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=120.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise LlmError(f"LLM request failed: {exc}") from exc

    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmError("Unexpected LLM response structure") from exc

    return _parse_llm_content(content)
