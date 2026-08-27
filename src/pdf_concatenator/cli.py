from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from pdf_concatenator.color_parse import DEFAULT_BACKGROUND, ColorParseError, parse_color
from pdf_concatenator.config import ConfigError, DEFAULT_CONFIG_PATH
from pdf_concatenator.discovery import DiscoveredPdf, discover_pdfs
from pdf_concatenator.llm import LlmError
from pdf_concatenator.pdf_build import DocumentInfo, PdfBuildError, build_concatenated_pdf
from pdf_concatenator.page_size_options import resolve_page_size_options
from pdf_concatenator.split import build_split_outputs, parse_max_output_size
from pdf_concatenator.summaries import load_llm_config, resolve_sidecar
from tqdm import tqdm


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf-concatenator",
        description="Concatenate PDFs with a table of contents and optional summaries.",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="filename",
        help="Output PDF filename (required unless --regenerate-summaries)",
    )
    parser.add_argument(
        "--include-summaries",
        action="store_true",
        help="Include summaries in the table of contents and cover pages",
    )
    parser.add_argument(
        "--regenerate-summaries",
        action="store_true",
        help="Regenerate sidecar summary files only; do not concatenate",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="pattern",
        help="Exclude files matching pattern (may be repeated)",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to LLM config file",
    )
    parser.add_argument(
        "--summary-instructions",
        metavar="TEXT",
        help=(
            "Extra instructions appended to the summarisation prompt for this run "
            "(e.g. how to derive the summary). Changing the text invalidates cached "
            "sidecars."
        ),
    )
    parser.add_argument(
        "--summary-instructions-file",
        metavar="PATH",
        help="Read the extra summarisation instructions from a file instead of --summary-instructions",
    )
    parser.add_argument(
        "--page-numbers",
        action="store_true",
        help="Superimpose running page numbers on the original PDF pages",
    )
    parser.add_argument(
        "--no-interstitial-pages",
        "--no-cover-pages",
        dest="interstitial_pages",
        action="store_false",
        help="Omit the per-document cover/separator pages (contents links point straight to each document)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show library warnings while reading and merging PDFs",
    )
    parser.add_argument(
        "--max-output-size",
        metavar="SIZE",
        help="Split output into parts no larger than SIZE (e.g. 50M, 2G)",
    )
    parser.add_argument(
        "--contents-background",
        default=DEFAULT_BACKGROUND,
        metavar="color",
        help="Background color for contents pages (default: #f3f2a3)",
    )
    parser.add_argument(
        "--cover-background",
        default=DEFAULT_BACKGROUND,
        metavar="color",
        help="Background color for cover pages (default: #f3f2a3)",
    )
    parser.add_argument(
        "--page-sizes",
        metavar="SIZES",
        help=(
            "Comma-separated paper sizes available on the printer (e.g. a4,a3); "
            "snaps every page to the closest match"
        ),
    )
    parser.add_argument(
        "--index-page-size",
        metavar="SIZE",
        help="Page size for contents/index pages (default: a4, or follows first document with --page-sizes)",
    )
    parser.add_argument(
        "--separator-page-size",
        metavar="SIZE",
        help="Page size for separator/cover pages (default: a4, or follows each document with --page-sizes)",
    )
    parser.add_argument("pattern", help="Directory or glob pattern for PDF files")
    return parser


def _configure_logging(verbose: bool) -> None:
    level = logging.WARNING if verbose else logging.ERROR
    logging.getLogger("pypdf").setLevel(level)


def _summary_progress(
    pdfs: list[DiscoveredPdf],
    *,
    disable: bool | None = None,
):
    if disable is None:
        disable = not sys.stderr.isatty()
    return tqdm(
        pdfs,
        desc="Summaries",
        unit="pdf",
        total=len(pdfs),
        disable=disable,
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_intermixed_args(argv)
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else 1

    _configure_logging(args.verbose)

    if args.regenerate_summaries:
        if args.output:
            print(
                "error: --output cannot be used with --regenerate-summaries",
                file=sys.stderr,
            )
            return 2
        return _regenerate_summaries(args)

    if not args.output:
        print(
            "error: the following arguments are required: -o/--output",
            file=sys.stderr,
        )
        return 2

    return _concatenate(args)


def _resolve_summary_instructions(args: argparse.Namespace) -> str | None:
    """Return the extra prompt text, or None if the arguments are inconsistent."""
    text = args.summary_instructions
    if args.summary_instructions_file:
        if text is not None:
            print(
                "error: use only one of --summary-instructions / --summary-instructions-file",
                file=sys.stderr,
            )
            return None
        try:
            text = Path(args.summary_instructions_file).read_text()
        except OSError as exc:
            print(f"error: cannot read --summary-instructions-file: {exc}", file=sys.stderr)
            return None
    return (text or "").strip()


def _discover(args: argparse.Namespace):
    pdfs = discover_pdfs(args.pattern, excludes=args.exclude)
    if not pdfs:
        print("No PDF files matched pattern.", file=sys.stderr)
        return None
    return pdfs


def _report_summary_failure(pdf: DiscoveredPdf, exc: LlmError) -> None:
    print(
        f"warning: skipping summary for {pdf.relative_path}: {exc}",
        file=sys.stderr,
    )


def _regenerate_summaries(args: argparse.Namespace) -> int:
    pdfs = _discover(args)
    if pdfs is None:
        return 1

    try:
        config = load_llm_config(Path(args.config))
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    instructions = _resolve_summary_instructions(args)
    if instructions is None:
        return 2

    for pdf in _summary_progress(pdfs):
        try:
            resolve_sidecar(
                pdf.path, config, force=True, extra_instructions=instructions
            )
        except LlmError as exc:
            _report_summary_failure(pdf, exc)

    return 0


def _parse_page_backgrounds(args: argparse.Namespace) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    try:
        return (
            parse_color(args.contents_background),
            parse_color(args.cover_background),
        )
    except ColorParseError as exc:
        print(str(exc), file=sys.stderr)
        return None


def _concatenate(args: argparse.Namespace) -> int:
    pdfs = _discover(args)
    if pdfs is None:
        return 1

    backgrounds = _parse_page_backgrounds(args)
    if backgrounds is None:
        return 1
    contents_background, cover_background = backgrounds

    page_size_options, page_size_error = resolve_page_size_options(
        config_path=Path(args.config),
        page_sizes=args.page_sizes,
        index_page_size=args.index_page_size,
        separator_page_size=args.separator_page_size,
    )
    if page_size_error is not None:
        print(page_size_error, file=sys.stderr)
        return 1

    output_path = Path(args.output)
    config = None
    summary_instructions = ""
    if args.include_summaries:
        try:
            config = load_llm_config(Path(args.config))
        except ConfigError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        resolved = _resolve_summary_instructions(args)
        if resolved is None:
            return 2
        summary_instructions = resolved

    documents: list[DocumentInfo] = []
    summary_pdfs = pdfs if args.include_summaries else []
    for pdf in _summary_progress(summary_pdfs) if summary_pdfs else pdfs:
        summary: str | None = None
        title = pdf.path.stem
        if args.include_summaries:
            assert config is not None
            try:
                sidecar = resolve_sidecar(
                    pdf.path,
                    config,
                    force=False,
                    extra_instructions=summary_instructions,
                )
            except LlmError as exc:
                _report_summary_failure(pdf, exc)
            else:
                summary = sidecar.summary
                title = sidecar.title

        documents.append(
            DocumentInfo(
                path=pdf.path,
                relative_path=pdf.relative_path,
                title=title,
                summary=summary,
            )
        )

    try:
        if args.max_output_size:
            max_bytes = parse_max_output_size(args.max_output_size)
            paths = build_split_outputs(
                documents,
                output_path,
                include_summaries=args.include_summaries,
                max_bytes=max_bytes,
                contents_background=contents_background,
                cover_background=cover_background,
                page_size_options=page_size_options,
                include_covers=args.interstitial_pages,
                stamp_page_numbers=args.page_numbers,
            )
            if len(paths) > 1:
                for path in paths:
                    print(path)
        else:
            print("Building concatenated PDF...", file=sys.stderr, flush=True)
            build_concatenated_pdf(
                documents,
                output_path,
                include_summaries=args.include_summaries,
                contents_background=contents_background,
                cover_background=cover_background,
                page_size_options=page_size_options,
                include_covers=args.interstitial_pages,
                stamp_page_numbers=args.page_numbers,
            )
    except PdfBuildError as exc:
        print(str(exc), file=sys.stderr)
        if output_path.exists():
            output_path.unlink()
        for part_path in output_path.parent.glob(f"{output_path.stem}_part_*{output_path.suffix}"):
            part_path.unlink(missing_ok=True)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
