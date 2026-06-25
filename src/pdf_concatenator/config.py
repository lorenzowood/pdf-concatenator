from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "pdf-concatenator"

DEFAULT_PROMPT = (
    "You are summarising a PDF document. Given the filename, metadata, and PDF "
    "below, produce a concise title and a summary under 100 words (ideally one "
    "sentence, but use more only if needed). Respond with JSON only: "
    '{"title": "...", "summary": "..."}'
)

REQUIRED_KEYS = ("LLM_API", "LLM_SERVER", "LLM_API_KEY", "LLM_MODEL")


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class LlmConfig:
    api: str
    server: str
    api_key: str
    model: str
    prompt: str


def _parse_config_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> LlmConfig:
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    values = _parse_config_text(path.read_text())
    for key in REQUIRED_KEYS:
        if key not in values or not values[key]:
            raise ConfigError(f"Missing required config key: {key}")

    return LlmConfig(
        api=values["LLM_API"],
        server=values["LLM_SERVER"],
        api_key=values["LLM_API_KEY"],
        model=values["LLM_MODEL"],
        prompt=values.get("LLM_PROMPT_TITLE_AND_SUMMARY", ""),
    )


def ensure_prompt(config: LlmConfig, path: Path = DEFAULT_CONFIG_PATH) -> LlmConfig:
    if config.prompt:
        return config
    try:
        existing = path.read_text()
        if existing and not existing.endswith("\n"):
            existing += "\n"
        path.write_text(
            existing + f"LLM_PROMPT_TITLE_AND_SUMMARY={DEFAULT_PROMPT}\n"
        )
    except OSError as exc:
        raise ConfigError(f"Failed to write default prompt to config: {exc}") from exc
    return LlmConfig(
        api=config.api,
        server=config.server,
        api_key=config.api_key,
        model=config.model,
        prompt=DEFAULT_PROMPT,
    )
