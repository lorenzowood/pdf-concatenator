from __future__ import annotations

from pathlib import Path

import pytest

from pdf_concatenator.config import (
    DEFAULT_PROMPT,
    ConfigError,
    LlmConfig,
    load_config,
    ensure_prompt,
)


class TestLoadConfig:
    def test_loads_key_value_pairs(self, tmp_path: Path):
        config_file = tmp_path / "config"
        config_file.write_text(
            "LLM_API=open_ai\n"
            "LLM_SERVER=127.0.0.1:28911\n"
            "LLM_API_KEY=secret\n"
            "LLM_MODEL=test-model\n"
            "LLM_PROMPT_TITLE_AND_SUMMARY=Do the thing\n"
        )
        cfg = load_config(config_file)
        assert cfg.api == "open_ai"
        assert cfg.server == "127.0.0.1:28911"
        assert cfg.api_key == "secret"
        assert cfg.model == "test-model"
        assert cfg.prompt == "Do the thing"

    def test_ignores_comments_and_blank_lines(self, tmp_path: Path):
        config_file = tmp_path / "config"
        config_file.write_text(
            "# comment\n"
            "\n"
            "LLM_API=open_ai\n"
            "LLM_SERVER=host:1\n"
            "LLM_API_KEY=k\n"
            "LLM_MODEL=m\n"
            "LLM_PROMPT_TITLE_AND_SUMMARY=p\n"
        )
        cfg = load_config(config_file)
        assert cfg.api == "open_ai"

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(ConfigError, match="not found"):
            load_config(tmp_path / "missing")

    def test_missing_required_key_raises(self, tmp_path: Path):
        config_file = tmp_path / "config"
        config_file.write_text("LLM_API=open_ai\n")
        with pytest.raises(ConfigError, match="LLM_SERVER"):
            load_config(config_file)


class TestEnsurePrompt:
    def test_writes_default_prompt_when_missing(self, tmp_path: Path):
        config_file = tmp_path / "config"
        config_file.write_text(
            "LLM_API=open_ai\n"
            "LLM_SERVER=127.0.0.1:28911\n"
            "LLM_API_KEY=secret\n"
            "LLM_MODEL=test-model\n"
        )
        cfg = ensure_prompt(load_config(config_file), config_file)
        assert cfg.prompt == DEFAULT_PROMPT
        saved = config_file.read_text()
        assert "LLM_PROMPT_TITLE_AND_SUMMARY=" in saved

    def test_does_not_overwrite_existing_prompt(self, tmp_path: Path):
        config_file = tmp_path / "config"
        config_file.write_text(
            "LLM_API=open_ai\n"
            "LLM_SERVER=127.0.0.1:28911\n"
            "LLM_API_KEY=secret\n"
            "LLM_MODEL=test-model\n"
            "LLM_PROMPT_TITLE_AND_SUMMARY=custom\n"
        )
        cfg = ensure_prompt(load_config(config_file), config_file)
        assert cfg.prompt == "custom"

    def test_raises_if_cannot_write_prompt(self, tmp_path: Path, monkeypatch):
        config_file = tmp_path / "config"
        config_file.write_text(
            "LLM_API=open_ai\n"
            "LLM_SERVER=127.0.0.1:28911\n"
            "LLM_API_KEY=secret\n"
            "LLM_MODEL=test-model\n"
        )

        def fail_write(*_args, **_kwargs):
            raise OSError("permission denied")

        monkeypatch.setattr(Path, "write_text", fail_write)
        with pytest.raises(ConfigError, match="prompt"):
            ensure_prompt(load_config(config_file), config_file)
