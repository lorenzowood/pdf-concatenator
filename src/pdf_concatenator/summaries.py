from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pdf_concatenator.config import LlmConfig, ensure_prompt, load_config
from pdf_concatenator.llm import generate_title_and_summary
from pdf_concatenator.sidecar import (
    Sidecar,
    is_sidecar_valid,
    load_sidecar,
    save_sidecar,
    sha256_file,
)


def resolve_sidecar(pdf_path: Path, config: LlmConfig, *, force: bool = False) -> Sidecar:
    if not force and is_sidecar_valid(pdf_path):
        loaded = load_sidecar(pdf_path)
        if loaded is not None:
            return loaded

    generated = generate_title_and_summary(config, pdf_path)
    sidecar = Sidecar(
        filename=pdf_path.name,
        sha256=sha256_file(pdf_path),
        title=generated.title,
        summary=generated.summary,
        generated_by=config.model,
        generated_on=datetime.now(timezone.utc).isoformat(),
    )
    save_sidecar(pdf_path, sidecar)
    return sidecar


def load_llm_config(config_path: Path | None = None) -> LlmConfig:
    path = config_path if config_path is not None else None
    from pdf_concatenator.config import DEFAULT_CONFIG_PATH

    config_file = path or DEFAULT_CONFIG_PATH
    return ensure_prompt(load_config(config_file), config_file)
