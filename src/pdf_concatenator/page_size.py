from __future__ import annotations

from dataclasses import dataclass

from pypdf import PageObject, Transformation
from reportlab.lib.pagesizes import A3, A4, A5, elevenSeventeen, legal, letter


class PageSizeParseError(Exception):
    pass


@dataclass(frozen=True)
class PageSize:
    width: float
    height: float
    name: str

    @property
    def pagesize(self) -> tuple[float, float]:
        return (self.width, self.height)

    def oriented(self, landscape_page: bool) -> PageSize:
        if landscape_page == (self.width > self.height):
            return self
        return PageSize(self.height, self.width, self.name)

    def as_portrait(self) -> PageSize:
        if self.height >= self.width:
            return self
        return PageSize(self.height, self.width, self.name)


_NAMED_SIZES: dict[str, PageSize] = {
    "a4": PageSize(A4[0], A4[1], "a4"),
    "a3": PageSize(A3[0], A3[1], "a3"),
    "a5": PageSize(A5[0], A5[1], "a5"),
    "letter": PageSize(letter[0], letter[1], "letter"),
    "legal": PageSize(legal[0], legal[1], "legal"),
    "tabloid": PageSize(elevenSeventeen[0], elevenSeventeen[1], "tabloid"),
    "ledger": PageSize(elevenSeventeen[0], elevenSeventeen[1], "ledger"),
}

DEFAULT_INDEX_PAGE_SIZE = _NAMED_SIZES["a4"]
DEFAULT_SEPARATOR_PAGE_SIZE = _NAMED_SIZES["a4"]


def parse_page_size(value: str) -> PageSize:
    key = value.strip().lower()
    if key not in _NAMED_SIZES:
        supported = ", ".join(sorted({name for name in _NAMED_SIZES}))
        raise PageSizeParseError(
            f"Unknown page size {value!r}; supported sizes: {supported}"
        )
    return _NAMED_SIZES[key]


def parse_page_size_list(value: str) -> tuple[PageSize, ...]:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        raise PageSizeParseError("Page size list must not be empty")
    return tuple(parse_page_size(part) for part in parts)


def effective_page_size(page: PageObject) -> tuple[float, float]:
    box = page.cropbox or page.mediabox
    width = float(box.width)
    height = float(box.height)
    rotation = int(page.get("/Rotate", 0)) % 360
    if rotation in (90, 270):
        width, height = height, width
    return width, height


def closest_page_size(
    width: float,
    height: float,
    allowed: tuple[PageSize, ...],
) -> PageSize:
    if not allowed:
        raise ValueError("allowed page sizes must not be empty")

    landscape_page = width > height
    best: PageSize | None = None
    best_distance = float("inf")

    for candidate in allowed:
        oriented = candidate.oriented(landscape_page)
        distance = (width - oriented.width) ** 2 + (height - oriented.height) ** 2
        if distance < best_distance:
            best_distance = distance
            best = oriented

    assert best is not None
    return best


def snap_page_to_size(page: PageObject, target: PageSize) -> PageObject:
    source_width, source_height = effective_page_size(page)
    target_width, target_height = target.width, target.height
    scale = min(target_width / source_width, target_height / source_height)
    scaled_width = source_width * scale
    scaled_height = source_height * scale
    translate_x = (target_width - scaled_width) / 2
    translate_y = (target_height - scaled_height) / 2

    new_page = PageObject.create_blank_page(
        width=target_width,
        height=target_height,
    )
    new_page.merge_transformed_page(
        page,
        Transformation()
        .scale(scale, scale)
        .translate(translate_x, translate_y),
    )
    return new_page
