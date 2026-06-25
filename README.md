# pdf-concatenator

Bundle many PDFs into a single submission-ready document.

This tool was built to pull together a large set of PDFs for a **contract submission**: one combined file with a table of contents, cover pages, and optional short summaries so reviewers can navigate the bundle easily.

## Features

- Recursively discover PDFs from a directory or glob pattern
- Sort files by path and concatenate them into one output PDF
- Generate a **table of contents** with folder structure, page numbers, and alternating row shading
- Insert a **cover page** before each source PDF (path, optional summary, page number)
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

Patterns can be a directory (all PDFs beneath it) or a glob, e.g. `contracts/**/*.pdf`.

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

## Output structure

1. **Contents** — tree of folders and files; page numbers point to each document's cover page. When summaries are included, a disclaimer appears in the footer.
2. **Cover page** per PDF — relative path, optional summary, page number.
3. **Original PDF pages** — unchanged (no added page numbers).

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
                        [--config CONFIG] [--verbose]
                        [--max-output-size SIZE]
                        pattern
```

| Option | Description |
|--------|-------------|
| `-o`, `--output` | Output PDF path (required unless `--regenerate-summaries`) |
| `--include-summaries` | Include summaries in contents and cover pages |
| `--regenerate-summaries` | Regenerate sidecar files only; do not concatenate |
| `--exclude` | Glob pattern to exclude (repeatable) |
| `--config` | Path to LLM config (default: `~/.config/pdf-concatenator`) |
| `--verbose` | Show library warnings while reading/merging PDFs |
| `--max-output-size` | Split output into parts under this size (e.g. `50M`, `2G`) |

## Development

```bash
pytest
```

## License

MIT
