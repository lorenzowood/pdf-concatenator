from __future__ import annotations

from pathlib import Path

from pdf_concatenator.config import load_optional_settings
from pdf_concatenator.page_size import (
    PageSize,
    PageSizeParseError,
    parse_page_size,
    parse_page_size_list,
)
from pdf_concatenator.pdf_build import PageSizeOptions


def resolve_page_size_options(
    *,
    config_path: Path,
    page_sizes: str | None,
    index_page_size: str | None,
    separator_page_size: str | None,
) -> tuple[PageSizeOptions | None, str | None]:
    settings = load_optional_settings(config_path)

    allowed: tuple[PageSize, ...] = ()
    if page_sizes is not None:
        try:
            allowed = parse_page_size_list(page_sizes)
        except PageSizeParseError as exc:
            return None, str(exc)
    elif settings.get("PAGE_SIZES"):
        try:
            allowed = parse_page_size_list(settings["PAGE_SIZES"])
        except PageSizeParseError as exc:
            return None, str(exc)

    index: PageSize | None = None
    if index_page_size is not None:
        try:
            index = parse_page_size(index_page_size)
        except PageSizeParseError as exc:
            return None, str(exc)
    elif settings.get("INDEX_PAGE_SIZE"):
        try:
            index = parse_page_size(settings["INDEX_PAGE_SIZE"])
        except PageSizeParseError as exc:
            return None, str(exc)

    separator: PageSize | None = None
    if separator_page_size is not None:
        try:
            separator = parse_page_size(separator_page_size)
        except PageSizeParseError as exc:
            return None, str(exc)
    elif settings.get("SEPARATOR_PAGE_SIZE"):
        try:
            separator = parse_page_size(settings["SEPARATOR_PAGE_SIZE"])
        except PageSizeParseError as exc:
            return None, str(exc)

    return (
        PageSizeOptions(
            allowed_sizes=allowed,
            index_page_size=index,
            separator_page_size=separator,
        ),
        None,
    )
