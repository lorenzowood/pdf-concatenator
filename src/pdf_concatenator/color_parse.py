from __future__ import annotations

import re

DEFAULT_BACKGROUND = "#f3f2a3"
DEFAULT_BACKGROUND_RGB = (0xF3 / 255, 0xF2 / 255, 0xA3 / 255)

_HEX_RE = re.compile(r"^#?([0-9a-f]{3}|[0-9a-f]{6})$", re.IGNORECASE)


class ColorParseError(ValueError):
    pass


def parse_color(value: str) -> tuple[float, float, float]:
    """Parse a hex color such as #f3f2a3 or fa3 into RGB components (0-1)."""
    match = _HEX_RE.match(value.strip())
    if not match:
        raise ColorParseError(f"Invalid color: {value!r}")

    hex_digits = match.group(1)
    if len(hex_digits) == 3:
        hex_digits = "".join(character * 2 for character in hex_digits)

    return (
        int(hex_digits[0:2], 16) / 255,
        int(hex_digits[2:4], 16) / 255,
        int(hex_digits[4:6], 16) / 255,
    )


def tint_with_black(
    rgb: tuple[float, float, float],
    opacity: float = 0.05,
) -> tuple[float, float, float]:
    """Blend RGB with black at the given opacity."""
    return tuple(channel * (1 - opacity) for channel in rgb)
