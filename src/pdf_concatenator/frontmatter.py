"""Read YAML-ish front matter from a companion file and evaluate a small
expression against it, to build a summary string from existing metadata.

Expression language
-------------------
* ``field``            - the value of a front-matter field (empty if absent)
* ``"text"``           - a literal string (``\\"`` and ``\\\\`` escapes)
* ``\\(``  ``\\)`` ...   - any ``\\x`` is the literal character ``x``
                         (``\\n`` / ``\\t`` are newline / tab)
* juxtaposition        - adjacent terms are concatenated; the whitespace
                         between them is only a separator and emits nothing
* ``cond ? a : b``     - if ``cond`` is non-empty use ``a`` else ``b``
* ``cond ? a``         - the ``: b`` is optional and defaults to empty
* ``( ... )``          - grouping

Because juxtaposition has no visible operator, an inline ``?:`` must be
parenthesised when anything follows it, e.g.::

    (original_headline ? original_headline ": ") summary " (" section ")"

A list value (``people: [a, b]``) stringifies as ``a, b``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


class FrontMatterExpressionError(ValueError):
    """Raised when a --summaries-from-frontmatter expression is malformed."""


# --------------------------------------------------------------------------- #
# Front matter parsing
# --------------------------------------------------------------------------- #

_FENCE_RE = re.compile(r"---\r?\n(.*?)\r?\n---", re.DOTALL)
_KEY_RE = re.compile(r"\s*([A-Za-z_][\w-]*)\s*:\s?(.*)$")


def _parse_scalar(raw: str) -> object:
    raw = raw.strip()
    if raw == "":
        return ""
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        return raw[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        return raw[1:-1].replace("''", "'")
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip("\"'") for item in inner.split(",")]
    return raw


def parse_front_matter(text: str) -> dict[str, object]:
    """Parse ``key: value`` lines from a front-matter block.

    Accepts a full ``---`` fenced Markdown file or a bare block (e.g. a
    ``.yaml`` sidecar). Only single-line scalars and inline ``[..]`` lists are
    understood, which is all this project's corpus uses.
    """
    text = text.lstrip("﻿")
    if text.lstrip().startswith("---"):
        match = _FENCE_RE.search(text)
        block = match.group(1) if match else ""
    else:
        block = text

    fields: dict[str, object] = {}
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _KEY_RE.match(line)
        if match:
            fields[match.group(1)] = _parse_scalar(match.group(2))
    return fields


def stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(stringify(item) for item in value)
    return str(value)


# --------------------------------------------------------------------------- #
# Expression: tokeniser
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class _Token:
    kind: str  # 'str' | 'ident' | 'char' | 'op'
    value: str


_ESCAPES = {"n": "\n", "t": "\t"}


def _tokenise(src: str) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    n = len(src)
    while i < n:
        ch = src[i]
        if ch.isspace():
            i += 1
            continue
        if ch in "?:()":
            tokens.append(_Token("op", ch))
            i += 1
            continue
        if ch == '"':
            i += 1
            buf: list[str] = []
            while i < n and src[i] != '"':
                if src[i] == "\\" and i + 1 < n:
                    nxt = src[i + 1]
                    buf.append(_ESCAPES.get(nxt, nxt))
                    i += 2
                else:
                    buf.append(src[i])
                    i += 1
            if i >= n:
                raise FrontMatterExpressionError("unterminated string literal")
            i += 1  # closing quote
            tokens.append(_Token("str", "".join(buf)))
            continue
        if ch == "\\":
            if i + 1 >= n:
                raise FrontMatterExpressionError("trailing backslash")
            nxt = src[i + 1]
            tokens.append(_Token("char", _ESCAPES.get(nxt, nxt)))
            i += 2
            continue
        match = re.match(r"[A-Za-z_][\w-]*", src[i:])
        if not match:
            raise FrontMatterExpressionError(f"unexpected character {ch!r}")
        tokens.append(_Token("ident", match.group(0)))
        i += match.end()
    return tokens


# --------------------------------------------------------------------------- #
# Expression: parser -> AST
# --------------------------------------------------------------------------- #

class _Node:
    def eval(self, fields: dict[str, object]) -> str:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass(frozen=True)
class _Literal(_Node):
    text: str

    def eval(self, fields: dict[str, object]) -> str:
        return self.text


@dataclass(frozen=True)
class _Field(_Node):
    name: str

    def eval(self, fields: dict[str, object]) -> str:
        return stringify(fields.get(self.name, ""))


@dataclass(frozen=True)
class _Concat(_Node):
    parts: tuple[_Node, ...]

    def eval(self, fields: dict[str, object]) -> str:
        return "".join(part.eval(fields) for part in self.parts)


@dataclass(frozen=True)
class _Ternary(_Node):
    cond: _Node
    if_true: _Node
    if_false: _Node

    def eval(self, fields: dict[str, object]) -> str:
        chosen = self.if_true if self.cond.eval(fields) != "" else self.if_false
        return chosen.eval(fields)


class _Parser:
    def __init__(self, tokens: list[_Token]) -> None:
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> _Token | None:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _next(self) -> _Token:
        token = self._tokens[self._pos]
        self._pos += 1
        return token

    def _at_op(self, *ops: str) -> bool:
        token = self._peek()
        return token is not None and token.kind == "op" and token.value in ops

    def parse(self) -> _Node:
        node = self._concat(stop=())
        if self._pos != len(self._tokens):
            token = self._tokens[self._pos]
            raise FrontMatterExpressionError(f"unexpected {token.value!r}")
        return node

    def _concat(self, stop: tuple[str, ...]) -> _Node:
        parts: list[_Node] = []
        while self._peek() is not None and not self._at_op(*stop):
            parts.append(self._term())
        if len(parts) == 1:
            return parts[0]
        return _Concat(tuple(parts))

    def _term(self) -> _Node:
        node = self._primary()
        if self._at_op("?"):
            self._next()
            if_true = self._concat(stop=(":", ")"))
            if_false: _Node = _Literal("")
            if self._at_op(":"):
                self._next()
                if_false = self._concat(stop=(")",))
            return _Ternary(node, if_true, if_false)
        return node

    def _primary(self) -> _Node:
        token = self._peek()
        if token is None:
            raise FrontMatterExpressionError("unexpected end of expression")
        if token.kind == "str":
            self._next()
            return _Literal(token.value)
        if token.kind == "char":
            self._next()
            return _Literal(token.value)
        if token.kind == "ident":
            self._next()
            return _Field(token.value)
        if token.kind == "op" and token.value == "(":
            self._next()
            inner = self._concat(stop=(")",))
            if not self._at_op(")"):
                raise FrontMatterExpressionError("missing ')'")
            self._next()
            return inner
        raise FrontMatterExpressionError(f"unexpected {token.value!r}")


@dataclass(frozen=True)
class SummaryExpression:
    source: str
    _ast: _Node

    def evaluate(self, fields: dict[str, object]) -> str:
        return self._ast.eval(fields)


def compile_expression(source: str) -> SummaryExpression:
    tokens = _tokenise(source)
    if not tokens:
        raise FrontMatterExpressionError("empty expression")
    ast = _Parser(tokens).parse()
    return SummaryExpression(source=source, _ast=ast)


# --------------------------------------------------------------------------- #
# Companion-file lookup
# --------------------------------------------------------------------------- #

_FRONT_MATTER_EXTS = (".md", ".markdown", ".yaml", ".yml")


def load_front_matter_for(pdf_path, frontmatter_dir=None) -> dict[str, object] | None:
    """Find and parse the front matter for ``pdf_path``.

    Looks for ``<stem><ext>`` (``.md``/``.markdown``/``.yaml``/``.yml``) in
    ``frontmatter_dir`` if given, otherwise beside the PDF. Returns ``None`` if
    nothing is found.
    """
    from pathlib import Path

    pdf_path = Path(pdf_path)
    search_dir = Path(frontmatter_dir) if frontmatter_dir else pdf_path.parent
    for ext in _FRONT_MATTER_EXTS:
        candidate = search_dir / f"{pdf_path.stem}{ext}"
        if candidate.is_file():
            return parse_front_matter(candidate.read_text(encoding="utf-8"))
    return None
