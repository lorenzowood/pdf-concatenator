# pdf-concatenator

Bundle many PDFs into a single submission-ready document.

This tool was built to pull together a large set of PDFs for a **contract submission**: one combined file with a table of contents, cover pages, and optional short summaries so reviewers can navigate the bundle easily.

## Features

- Recursively discover PDFs from a directory or glob pattern
- Sort files by path and concatenate them into one output PDF
- Generate a **table of contents** with folder structure, page numbers, and alternating row shading
- Insert a **cover page** before each source PDF (path, optional summary, page number), or omit them entirely (`--no-interstitial-pages`)
- Optionally **superimpose running page numbers** on the source pages (`--page-numbers`)
- Tinted **background colours** on contents and cover pages so they stand out when scrolling (default: legal-pad yellow)
- Optionally generate **LLM summaries** via a sidecar file per PDF (`*.pdf.sidecar.json`)
- Regenerate sidecars without concatenating (`--regenerate-summaries`)
- Exclude specific files or patterns (`--exclude`)
- Progress bar while summaries are processed

## Installation

With [pipx](https://pipx.pypa.io/) (recommended):

```bash
pipx install pdf-concatenator
```

With pip:

```bash
pip install pdf-concatenator
```

For development:

```bash
git clone https://github.com/lorenzowood/pdf-concatenator.git
cd pdf-concatenator
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Quick start

Concatenate all PDFs under a folder:

```bash
pdf-concatenator -o submission.pdf contracts/
```

With summaries (requires LLM config — see below):

```bash
pdf-concatenator -o submission.pdf --include-summaries contracts/
```

Regenerate sidecar summaries only:

```bash
pdf-concatenator --regenerate-summaries contracts/
```

Exclude files:

```bash
pdf-concatenator -o submission.pdf \
  --exclude "drafts/*" \
  --exclude "broken.pdf" \
  contracts/
```

Patterns can be a directory (all PDFs beneath it) or a glob. A glob that matches a folder — e.g. `Comp*` matching `Comptons extension/` — includes all PDFs inside it. Quote patterns that contain spaces or shell metacharacters.

Customise the tinted backgrounds on contents and cover pages (hex colours, default `#f3f2a3`):

```bash
pdf-concatenator -o submission.pdf \
  --contents-background "#f3f2a3" \
  --cover-background "#f3f2a3" \
  contracts/
```

Alternating row stripes in the contents are derived from the contents background (5% black overlay), so they stay readable on any colour.

### One continuous document

To bundle many PDFs into a single flowing document — no separator pages, with page
numbers stamped on every page so the contents entries are usable:

```bash
pdf-concatenator -o combined.pdf --no-interstitial-pages --page-numbers posts/
```

`--no-interstitial-pages` (alias `--no-cover-pages`) drops the per-document cover
pages; the table of contents then links straight to each document's first page.
`--page-numbers` overlays a running page number, centred at the foot of each
source page, numbered by absolute position in the output (so it matches both the
contents and the PDF viewer). The two options are independent.

## LLM configuration

When using `--include-summaries` or `--regenerate-summaries`, create `~/.config/pdf-concatenator`:

```ini
LLM_API=open_ai
LLM_SERVER=127.0.0.1:28911
LLM_API_KEY=your-api-key
LLM_MODEL=your-model-id
LLM_PROMPT_TITLE_AND_SUMMARY=Your prompt here
```

The server should expose an OpenAI-compatible `/v1/chat/completions` endpoint. The whole PDF is sent to the model. If the prompt key is missing but everything else is valid, a default prompt is written to the config file.

Summaries are stored beside each PDF as `document.pdf.sidecar.json` and reused when the file hash matches.

### Summaries from front matter (no LLM)

If each PDF has a companion Markdown/YAML file with usable metadata, build the
summaries from it directly — no model, near-instant, exact text:

```bash
pdf-concatenator -o combined.pdf --no-interstitial-pages \
  --frontmatter-dir ./posts-src \
  --summaries-from-frontmatter '(original_headline ? original_headline ": ") summary " (" section ")"' \
  ./posts-pdf/
```

For each `posts-pdf/<name>.pdf` it reads `<name>.md` (or `.markdown` / `.yaml` /
`.yml`) — from `--frontmatter-dir` if given, otherwise beside the PDF — parses the
leading `---` front-matter block, and evaluates the expression to produce that
document's summary. No sidecar files are written. The "generated automatically"
disclaimer is omitted in this mode.

**Expression language:**

| Form | Meaning |
| --- | --- |
| `field` | the value of a front-matter field (empty string if absent) |
| `"text"` | a literal string (`\"` and `\\` escapes; `\n`, `\t`) |
| `\(` `\)` `\ ` … | any `\x` is the literal character `x` |
| `a b c` | adjacent terms are concatenated; the whitespace between them is only a separator and emits nothing |
| `cond ? a : b` | if `cond` evaluates non-empty, use `a`, else `b` |
| `cond ? a` | the `: b` is optional and defaults to empty |
| `( … )` | grouping |

A list value (`people: [a, b]`) stringifies as `a, b`. Because juxtaposition has
no visible operator, an inline `? :` must be parenthesised when anything follows
it — `(headline ? headline ": ") summary`, not `headline ? headline ": " summary`.

### Per-run summary instructions

`--summary-instructions "TEXT"` appends extra guidance to the prompt for one run,
without editing the config file. `--summary-instructions-file PATH` reads the same
text from a file. The instructions are recorded in each sidecar, so changing them
invalidates the cache and the affected summaries are regenerated on the next run.

For example, when every PDF carries a usable summary in its own front matter:

```bash
pdf-concatenator -o combined.pdf --no-interstitial-pages --include-summaries \
  --summary-instructions "These PDFs all have YAML front matter. Take the summary \
from the front-matter 'summary:' field verbatim; do not write a new one from the body." \
  posts/
```

## Output structure

1. **Contents** — tree of folders and files; page numbers point to each document's cover page. Alternating rows are shaded. When summaries are included, a disclaimer appears in the footer.
2. **Cover page** per PDF — relative path, optional summary, page number. Both contents and cover pages use a tinted background (legal-pad yellow by default). Suppressed by `--no-interstitial-pages`.
3. **Original PDF pages** — unchanged, unless `--page-numbers` is given, in which case a running page number is superimposed at the foot of each page.

If any PDF cannot be read, or summary generation fails when required, the run aborts and no output file is produced.

## Splitting large outputs

Upload limits (e.g. 50 MB) can be handled by splitting:

```bash
pdf-concatenator -o submission.pdf --max-output-size 50M contracts/
```

This produces `submission_part_1.pdf`, `submission_part_2.pdf`, and so on. Each part stays under the limit. Every part includes the **full table of contents**; entries in other parts are labelled `Part 2`, `Part 3`, etc. Under the **Contents** heading, each part also notes:

> This archive is split into n parts. This is part m.

If everything fits in one file, the original output name is used with no `_part_` suffix.

## Options

```
usage: pdf-concatenator [-h] [-o filename] [--include-summaries]
                        [--regenerate-summaries] [--exclude pattern]
                        [--config CONFIG] [--summary-instructions TEXT]
                        [--summary-instructions-file PATH]
                        [--summaries-from-frontmatter EXPR]
                        [--frontmatter-dir DIR] [--page-numbers]
                        [--no-interstitial-pages] [--verbose]
                        [--max-output-size SIZE]
                        [--contents-background color]
                        [--cover-background color]
                        pattern
```

| Option | Description |
|--------|-------------|
| `-o`, `--output` | Output PDF path (required unless `--regenerate-summaries`) |
| `--include-summaries` | Include summaries in contents and cover pages |
| `--regenerate-summaries` | Regenerate sidecar files only; do not concatenate |
| `--page-numbers` | Superimpose running page numbers on the original PDF pages |
| `--no-interstitial-pages` | Omit the per-document cover pages (alias `--no-cover-pages`) |
| `--exclude` | Glob pattern to exclude (repeatable) |
| `--config` | Path to LLM config (default: `~/.config/pdf-concatenator`) |
| `--summary-instructions` | Extra text appended to the summarisation prompt for this run |
| `--summary-instructions-file` | Read the extra summarisation instructions from a file |
| `--summaries-from-frontmatter` | Build summaries from companion front matter via an expression (no LLM) |
| `--frontmatter-dir` | Where to find the `<stem>.md`/`.yaml` companion files (default: beside each PDF) |
| `--verbose` | Show library warnings while reading/merging PDFs |
| `--max-output-size` | Split output into parts under this size (e.g. `50M`, `2G`) |
| `--contents-background` | Background colour for contents pages (default: `#f3f2a3`) |
| `--cover-background` | Background colour for cover pages (default: `#f3f2a3`) |

## Development

```bash
pytest
```

Release history is in [CHANGELOG.md](CHANGELOG.md).

## License

MIT
