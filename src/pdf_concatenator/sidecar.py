from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Sidecar:
    filename: str
    sha256: str
    title: str
    summary: str
    generated_by: str
    generated_on: str


def sidecar_path_for(pdf_path: Path) -> Path:
    return pdf_path.parent / f"{pdf_path.name}.sidecar.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _to_json_dict(sidecar: Sidecar) -> dict[str, str]:
    return {
        "filename": sidecar.filename,
        "sha256": sidecar.sha256,
        "title": sidecar.title,
        "summary": sidecar.summary,
        "generated-by": sidecar.generated_by,
        "generated-on": sidecar.generated_on,
    }


def _from_json_dict(data: dict) -> Sidecar:
    return Sidecar(
        filename=data["filename"],
        sha256=data["sha256"],
        title=data["title"],
        summary=data["summary"],
        generated_by=data["generated-by"],
        generated_on=data["generated-on"],
    )


def save_sidecar(pdf_path: Path, sidecar: Sidecar) -> Path:
    path = sidecar_path_for(pdf_path)
    path.write_text(json.dumps(_to_json_dict(sidecar), indent=4) + "\n")
    return path


def load_sidecar(pdf_path: Path) -> Sidecar | None:
    path = sidecar_path_for(pdf_path)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return _from_json_dict(data)


def is_sidecar_valid(pdf_path: Path) -> bool:
    sidecar = load_sidecar(pdf_path)
    if sidecar is None:
        return False
    return sidecar.sha256 == sha256_file(pdf_path)
