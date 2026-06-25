from __future__ import annotations

import pytest

from pdf_concatenator.color_parse import (
    DEFAULT_BACKGROUND_RGB,
    ColorParseError,
    parse_color,
    tint_with_black,
)


class TestParseColor:
    def test_parses_six_digit_hex_with_hash(self):
        assert parse_color("#f3f2a3") == DEFAULT_BACKGROUND_RGB

    def test_parses_six_digit_hex_without_hash(self):
        assert parse_color("f3f2a3") == DEFAULT_BACKGROUND_RGB

    def test_parses_three_digit_hex(self):
        assert parse_color("#fa3") == pytest.approx((1.0, 170 / 255, 51 / 255))

    def test_rejects_invalid_color(self):
        with pytest.raises(ColorParseError):
            parse_color("not-a-color")


class TestTintWithBlack:
    def test_tints_background_by_five_percent(self):
        tinted = tint_with_black(DEFAULT_BACKGROUND_RGB, opacity=0.05)
        assert tinted == pytest.approx(
            tuple(channel * 0.95 for channel in DEFAULT_BACKGROUND_RGB)
        )
