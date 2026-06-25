from __future__ import annotations

import re

class SizeParseError(ValueError):
    pass


_SIZE_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*([KMG]B?)?\s*$",
    re.IGNORECASE,
)

_UNITS = {
    "": 1,
    "K": 1024,
    "KB": 1024,
    "M": 1024**2,
    "MB": 1024**2,
    "G": 1024**3,
    "GB": 1024**3,
}


def parse_size(value: str) -> int:
    """Parse a size string such as 50M, 2G, or 1048576 into bytes."""
    match = _SIZE_RE.match(value)
    if not match:
        raise SizeParseError(f"Invalid size: {value!r}")

    number = float(match.group(1))
    unit = (match.group(2) or "").upper()
    if unit == "B":
        unit = ""
    multiplier = _UNITS.get(unit)
    if multiplier is None:
        raise SizeParseError(f"Invalid size unit in: {value!r}")

    return int(number * multiplier)
