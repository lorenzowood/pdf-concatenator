from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pdf_concatenator.sidecar import (
    Sidecar,
    sidecar_path_for,
    load_sidecar,
    save_sidecar,
    sha256_file,
    is_sidecar_valid,
)


class TestSidecarPath:
    def test_sidecar_path_appended_to_pdf_name(self, tmp_path: Path):
        pdf = tmp_path / "abc123.pdf"
        assert sidecar_path_for(pdf) == tmp_path / "abc123.pdf.sidecar.json"


class TestSha256:
    def test_hash_matches_file_content(self, tmp_path: Path):
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"hello pdf")
        assert sha256_file(pdf) == hashlib.sha256(b"hello pdf").hexdigest()


class TestSidecarRoundTrip:
    def test_save_and_load(self, tmp_path: Path):
        pdf = tmp_path / "report.pdf"
        pdf.write_bytes(b"content")
        sidecar = Sidecar(
            filename="report.pdf",
            sha256=sha256_file(pdf),
            title="Annual Report",
            summary="A brief annual report.",
            generated_by="test-model",
            generated_on="2026-06-25T10:00:00+00:00",
        )
        path = save_sidecar(pdf, sidecar)
        loaded = load_sidecar(pdf)
        assert loaded == sidecar
        assert path.exists()

    def test_load_missing_returns_none(self, tmp_path: Path):
        pdf = tmp_path / "missing.pdf"
        pdf.write_bytes(b"x")
        assert load_sidecar(pdf) is None


class TestSidecarValidation:
    def test_valid_when_hash_matches(self, tmp_path: Path):
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"same content")
        sidecar = Sidecar(
            filename="doc.pdf",
            sha256=sha256_file(pdf),
            title="T",
            summary="S",
            generated_by="m",
            generated_on="2026-01-01T00:00:00+00:00",
        )
        save_sidecar(pdf, sidecar)
        assert is_sidecar_valid(pdf) is True

    def test_invalid_when_hash_mismatches(self, tmp_path: Path):
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"original")
        sidecar = Sidecar(
            filename="doc.pdf",
            sha256="deadbeef",
            title="T",
            summary="S",
            generated_by="m",
            generated_on="2026-01-01T00:00:00+00:00",
        )
        save_sidecar(pdf, sidecar)
        assert is_sidecar_valid(pdf) is False

    def test_invalid_when_missing(self, tmp_path: Path):
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"x")
        assert is_sidecar_valid(pdf) is False


class TestSidecarSchema:
    def test_rejects_unknown_fields_on_load(self, tmp_path: Path):
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"x")
        sc_path = sidecar_path_for(pdf)
        sc_path.write_text(
            json.dumps(
                {
                    "filename": "doc.pdf",
                    "sha256": sha256_file(pdf),
                    "title": "T",
                    "summary": "S",
                    "generated-by": "m",
                    "generated-on": "2026-01-01T00:00:00+00:00",
                    "extra": "nope",
                }
            )
        )
        loaded = load_sidecar(pdf)
        assert loaded is not None
        assert not hasattr(loaded, "extra")

    def test_json_uses_hyphenated_keys(self, tmp_path: Path):
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"x")
        sidecar = Sidecar(
            filename="doc.pdf",
            sha256=sha256_file(pdf),
            title="T",
            summary="S",
            generated_by="model-1",
            generated_on="2026-06-25T12:00:00+00:00",
        )
        save_sidecar(pdf, sidecar)
        raw = json.loads(sidecar_path_for(pdf).read_text())
        assert raw["generated-by"] == "model-1"
        assert raw["generated-on"] == "2026-06-25T12:00:00+00:00"
