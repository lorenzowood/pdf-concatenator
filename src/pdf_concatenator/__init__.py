"""PDF concatenator with TOC, cover pages, and optional LLM summaries."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pdf-concatenator")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0.dev0"
