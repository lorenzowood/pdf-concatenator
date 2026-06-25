from __future__ import annotations

from pathlib import Path

import pytest

from pdf_concatenator.discovery import discover_pdfs


class TestDiscoverPdfs:
    def test_finds_pdfs_recursively_sorted_by_path(self, sample_tree: Path):
        results = discover_pdfs(str(sample_tree))
        rel_paths = [r.relative_path for r in results]
        assert rel_paths == sorted(rel_paths)
        assert len(results) == 4
        assert all(r.path.suffix.lower() == ".pdf" for r in results)

    def test_ignores_non_pdf_files(self, sample_tree: Path):
        results = discover_pdfs(str(sample_tree))
        names = {r.path.name for r in results}
        assert "readme.txt" not in names
        assert "notes.md" not in names

    def test_directory_pattern_finds_all_nested_pdfs(self, sample_tree: Path):
        results = discover_pdfs(str(sample_tree))
        rel = {r.relative_path for r in results}
        assert "reports/2024/jan.pdf" in rel
        assert "reports/2023/annual.pdf" in rel
        assert "summary.pdf" in rel

    def test_glob_pattern_matches_by_name(self, sample_tree: Path, tmp_path: Path):
        results = discover_pdfs(str(sample_tree / "reports" / "**" / "jan.pdf"))
        assert len(results) == 1
        assert results[0].relative_path == "reports/2024/jan.pdf"

    def test_glob_from_cwd_without_directory(self, sample_tree: Path, tmp_path: Path):
        results = discover_pdfs(str(tmp_path / "**" / "*.pdf"))
        assert len(results) == 4

    def test_empty_when_no_matches(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        results = discover_pdfs(str(empty))
        assert results == []

    def test_exclude_single_file(self, sample_tree: Path):
        results = discover_pdfs(
            str(sample_tree),
            excludes=["reports/2024/jan.pdf"],
        )
        rel = {r.relative_path for r in results}
        assert "reports/2024/jan.pdf" not in rel
        assert len(results) == 3

    def test_exclude_glob_pattern(self, sample_tree: Path):
        results = discover_pdfs(
            str(sample_tree),
            excludes=["reports/2024/*"],
        )
        rel = {r.relative_path for r in results}
        assert "reports/2024/jan.pdf" not in rel
        assert "reports/2024/feb.pdf" not in rel
        assert "reports/2023/annual.pdf" in rel

    def test_multiple_excludes(self, sample_tree: Path):
        results = discover_pdfs(
            str(sample_tree),
            excludes=["summary.pdf", "reports/2023/*"],
        )
        rel = {r.relative_path for r in results}
        assert rel == {"reports/2024/feb.pdf", "reports/2024/jan.pdf"}

    def test_paths_are_absolute(self, sample_tree: Path):
        results = discover_pdfs(str(sample_tree))
        for r in results:
            assert r.path.is_absolute()
            assert r.path.exists()

    def test_relative_path_uses_forward_slashes(self, sample_tree: Path):
        results = discover_pdfs(str(sample_tree))
        for r in results:
            assert "\\" not in r.relative_path
