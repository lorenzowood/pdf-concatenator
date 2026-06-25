from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pdf_concatenator.config import ConfigError, DEFAULT_CONFIG_PATH
from pdf_concatenator.discovery import discover_pdfs
from pdf_concatenator.llm import LlmError
from pdf_concatenator.pdf_build import DocumentInfo, PdfBuildError, build_concatenated_pdf
from pdf_concatenator.summaries import load_llm_config, resolve_sidecar


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
    parser.add_argument("pattern", help="Directory or glob pattern for PDF files")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else 1

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


def _discover(args: argparse.Namespace):
    pdfs = discover_pdfs(args.pattern, excludes=args.exclude)
    if not pdfs:
        print("No PDF files matched pattern.", file=sys.stderr)
        return None
    return pdfs


def _regenerate_summaries(args: argparse.Namespace) -> int:
    pdfs = _discover(args)
    if pdfs is None:
        return 1

    try:
        config = load_llm_config(Path(args.config))
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    for pdf in pdfs:
        try:
            resolve_sidecar(pdf.path, config, force=True)
        except LlmError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    return 0


def _concatenate(args: argparse.Namespace) -> int:
    pdfs = _discover(args)
    if pdfs is None:
        return 1

    output_path = Path(args.output)
    config = None
    if args.include_summaries:
        try:
            config = load_llm_config(Path(args.config))
        except ConfigError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    documents: list[DocumentInfo] = []
    for pdf in pdfs:
        summary: str | None = None
        title = pdf.path.stem
        if args.include_summaries:
            assert config is not None
            try:
                sidecar = resolve_sidecar(pdf.path, config, force=False)
            except LlmError as exc:
                print(str(exc), file=sys.stderr)
                return 1
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
        build_concatenated_pdf(
            documents,
            output_path,
            include_summaries=args.include_summaries,
        )
    except PdfBuildError as exc:
        print(str(exc), file=sys.stderr)
        if output_path.exists():
            output_path.unlink()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
