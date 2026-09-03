# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
semantic versioning.

## [1.4.0] - 2026-08-28

### Added
- `--summaries-from-frontmatter EXPR` builds each summary from a companion
  Markdown/YAML file's YAML front matter, using a small expression language — no
  LLM call, near-instant, exact text. Supports front-matter fields, string
  literals, `\x` escapes, juxtaposition concatenation, `cond ? a : b` (with an
  optional `: b`), and `( … )` grouping. See the README for the full grammar.
- `--frontmatter-dir DIR` points at the directory holding the `<stem>.md` /
  `.markdown` / `.yaml` / `.yml` companion files (default: beside each PDF).

### Changed
- The "Summaries are generated automatically and may contain errors." footer is
  suppressed when summaries come from front matter rather than the LLM.
- No sidecar files are written in front-matter mode.

## [1.3.0] - 2026-08-27

### Added
- `--summary-instructions TEXT` (and `--summary-instructions-file PATH`) append
  extra guidance to the summarisation prompt for a single run without editing the
  config file. The text is recorded in each sidecar, so changing it invalidates
  the cache and the affected summaries regenerate.

## [1.2.0] - 2026-08-27

### Added
- `--page-numbers` superimposes a running page number (absolute position in the
  output, centred at the foot) on every original PDF page.
- `--no-interstitial-pages` (alias `--no-cover-pages`) omits the per-document
  cover pages; the table of contents then links straight to each document's first
  page.

## [1.1.7] - 2026-07-04

### Changed
- Portrait index pages; more resilient summary handling.

## [1.1.6] - 2026-07-04

### Added
- Page-size snapping (`--page-sizes`, `--index-page-size`, `--separator-page-size`)
  and A4 defaults.

## [1.1.4] - 2026

### Added
- Tinted page backgrounds (`--contents-background`, `--cover-background`) and
  table-of-contents layout fixes.

## [1.1.0] - 2026

### Added
- `--max-output-size` splits the archive into size-limited parts, each carrying
  the full table of contents.

## [1.0.0] - 2026-06-25

### Added
- Initial release: recursive PDF discovery, concatenation in path order, a
  generated table of contents with folder structure and page numbers, a cover
  page before each source PDF, optional LLM-generated summaries via a per-file
  sidecar, and `--exclude` patterns.

[1.4.0]: https://github.com/lorenzowood/pdf-concatenator/releases/tag/v1.4.0
[1.3.0]: https://github.com/lorenzowood/pdf-concatenator/releases/tag/v1.3.0
[1.2.0]: https://github.com/lorenzowood/pdf-concatenator/releases/tag/v1.2.0
[1.1.7]: https://github.com/lorenzowood/pdf-concatenator/releases/tag/v1.1.7
[1.1.6]: https://github.com/lorenzowood/pdf-concatenator/releases/tag/v1.1.6
