from __future__ import annotations

import pytest

from pdf_concatenator.size_parse import SizeParseError, parse_size


class TestParseSize:
    def test_megabytes(self):
        assert parse_size("50M") == 50 * 1024 * 1024
        assert parse_size("50MB") == 50 * 1024 * 1024
        assert parse_size("50m") == 50 * 1024 * 1024

    def test_gigabytes(self):
        assert parse_size("2G") == 2 * 1024 * 1024 * 1024
        assert parse_size("2GB") == 2 * 1024 * 1024 * 1024

    def test_kilobytes(self):
        assert parse_size("512K") == 512 * 1024

    def test_decimal(self):
        assert parse_size("1.5M") == int(1.5 * 1024 * 1024)

    def test_bytes(self):
        assert parse_size("1048576") == 1048576

    def test_invalid_raises(self):
        with pytest.raises(SizeParseError):
            parse_size("fifty")
        with pytest.raises(SizeParseError):
            parse_size("50X")
