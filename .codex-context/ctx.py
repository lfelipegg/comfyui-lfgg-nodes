#!/usr/bin/env python3
"""Project-local context CLI for Codex.

Standard-library only. Stores a SQLite FTS index of selected Markdown files so
agents can search first and read bounded chunks by ID.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any, Iterable

DEFAULT_INCLUDE = [
    "README.md",
    "docs/**/*.md",
    "docs/**/*.mdx",
    "agents/**/*.md",
    ".codex-context/notes/**/*.md",
]
DEFAULT_EXCLUDE = [
    ".git/**",
    ".worktrees/**",
    "node_modules/**",
    "vendor/**",
    "dist/**",
    "build/**",
    ".next/**",
    "coverage/**",
    ".venv/**",
    "venv/**",
    "**/.env*",
    "**/*secret*",
    "**/*credential*",
    "**/*private-key*",
    "reference/**",
]
DEFAULT_CONFIG = """version = 1

db_path = ".codex-context/context.sqlite"

[sources]
include = [
  "README.md",
  "docs/**/*.md",
  "docs/**/*.mdx",
  "agents/**/*.md",
  ".codex-context/notes/**/*.md"
]
exclude = [
  ".git/**",
  ".worktrees/**",
  "node_modules/**",
  "vendor/**",
  "dist/**",
  "build/**",
  ".next/**",
  "coverage/**",
  ".venv/**",
  "venv/**",
  "**/.env*",
  "**/*secret*",
  "**/*credential*",
  "**/*private-key*",
  "reference/**"
]

[chunking]
target_chars = 3000
max_chars = 4000

[output]
search_limit_default = 5
read_max_chars_default = 4000
read_max_chars_hard = 12000
"""

SEMANTIC_ALIASES = {
    "auth": ["authentication", "authenticate", "login", "signin", "sign-in", "session", "password"],
    "authentication": ["auth", "authenticate", "login", "signin", "sign-in", "session", "password"],
    "login": ["auth", "authentication", "authenticate", "signin", "sign-in", "session", "password"],
    "signin": ["auth", "authentication", "login", "session"],
    "billing": ["payment", "payments", "invoice", "invoices", "subscription", "subscriptions", "plan", "plans", "charge", "charges"],
    "invoice": ["billing", "payment", "payments", "subscription", "charge"],
    "invoices": ["billing", "payment", "payments", "subscription", "charges"],
    "payment": ["billing", "invoice", "invoices", "subscription", "charge"],
    "payments": ["billing", "invoice", "invoices", "subscription", "charges"],
    "subscription": ["billing", "payment", "payments", "invoice", "plan"],
    "subscriptions": ["billing", "payment", "payments", "invoices", "plans"],
}

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"(?i)\bAWS_(?:ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN)\b\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{16,}['\"]?"),
    re.compile(r"\b(?:AKIA|ASIA|AIDA|AROA)[A-Z0-9]{16}\b"),
    re.compile(r"\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|token|secret|password)\b\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{16,}['\"]?"),
]
MAX_RESULT_LIMIT = 50


class ConfigError(RuntimeError):
    pass

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY,
  path TEXT UNIQUE NOT NULL,
  title TEXT,
  kind TEXT NOT NULL,
  hash TEXT NOT NULL,
  updated_at TEXT,
  indexed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL,
  path TEXT NOT NULL,
  title TEXT,
  heading TEXT,
  anchor TEXT,
  ordinal INTEGER NOT NULL,
  summary TEXT,
  content TEXT NOT NULL,
  tokens_estimate INTEGER,
  updated_at TEXT,
  indexed_at TEXT NOT NULL,
  FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  chunk_id UNINDEXED,
  title,
  path,
  heading,
  summary,
  content
);
"""


def fts_unavailable(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return "no such module: fts5" in message or "no such table: chunks_fts" in message


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".codex-context").exists() or (candidate / ".git").exists() or (candidate / "AGENTS.md").exists():
            return candidate
    return current


def command_root(repo: str | None) -> Path:
    return Path(repo).resolve() if repo else find_repo_root()


def strip_toml_comment(line: str) -> str:
    quote = ""
    escaped = False
    for idx, ch in enumerate(line):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if quote:
            if ch == quote:
                quote = ""
            continue
        if ch in {"'", '"'}:
            quote = ch
            continue
        if ch == "#":
            return line[:idx]
    return line


def parse_toml_scalar(value: str, line_no: int) -> Any:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    raise ConfigError(f"invalid config line {line_no}: unsupported value {value!r}")


def parse_toml_array(value: str, lines: list[str], index: int, line_no: int) -> tuple[list[Any], int]:
    raw = value.strip()
    items: list[Any] = []
    if raw == "[":
        index += 1
        while index < len(lines):
            item_line = strip_toml_comment(lines[index]).strip()
            if not item_line:
                index += 1
                continue
            if item_line == "]":
                return items, index
            if item_line.endswith(","):
                item_line = item_line[:-1].strip()
            items.append(parse_toml_scalar(item_line, index + 1))
            index += 1
        raise ConfigError(f"invalid config line {line_no}: unterminated array")
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return [], index
        for part in inner.split(","):
            part = part.strip()
            if part:
                items.append(parse_toml_scalar(part, line_no))
        return items, index
    raise ConfigError(f"invalid config line {line_no}: malformed array")


def parse_simple_toml(text: str) -> dict[str, Any]:
    """Parse the generated config shape on Python versions without tomllib."""
    data: dict[str, Any] = {}
    current = data
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line_no = index + 1
        stripped = strip_toml_comment(lines[index]).strip()
        if not stripped:
            index += 1
            continue
        if stripped.startswith("["):
            if not stripped.endswith("]") or stripped.count("[") != 1 or stripped.count("]") != 1:
                raise ConfigError(f"invalid config line {line_no}: malformed section")
            section = stripped[1:-1].strip()
            if not section or "." in section:
                raise ConfigError(f"invalid config line {line_no}: unsupported section {section!r}")
            current = data.setdefault(section, {})
            if not isinstance(current, dict):
                raise ConfigError(f"invalid config line {line_no}: section conflicts with value")
            index += 1
            continue
        if "=" not in stripped:
            raise ConfigError(f"invalid config line {line_no}: expected key = value")
        key, raw_value = stripped.split("=", 1)
        key = key.strip()
        if not key:
            raise ConfigError(f"invalid config line {line_no}: empty key")
        raw_value = raw_value.strip()
        if raw_value.startswith("["):
            value, index = parse_toml_array(raw_value, lines, index, line_no)
        else:
            value = parse_toml_scalar(raw_value, line_no)
        current[key] = value
        index += 1
    return data


def load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            return parse_simple_toml(path.read_text(encoding="utf-8"))
        except ConfigError as exc:
            raise ConfigError(f"invalid config: {exc}") from exc
        except Exception as exc:
            raise ConfigError(f"invalid config: {exc}") from exc
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except Exception as exc:
        raise ConfigError(f"invalid config: {exc}") from exc


def context_dir(root: Path) -> Path:
    resolved_root = root.resolve()
    resolved_context = (resolved_root / ".codex-context").resolve()
    try:
        resolved_context.relative_to(resolved_root)
    except ValueError as exc:
        raise ConfigError(".codex-context must stay within the repository") from exc
    return resolved_context


def positive_config_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{name} must be a positive integer")
    return value


def config_string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ConfigError(f"{name} must be a list of non-empty strings")
    return value


def config(root: Path) -> dict[str, Any]:
    cfg = load_toml(context_dir(root) / "config.toml")
    sources = cfg.get("sources", {}) if isinstance(cfg.get("sources", {}), dict) else {}
    chunking = cfg.get("chunking", {}) if isinstance(cfg.get("chunking", {}), dict) else {}
    output = cfg.get("output", {}) if isinstance(cfg.get("output", {}), dict) else {}
    result = {
        "db_path": cfg.get("db_path", ".codex-context/context.sqlite"),
        "include": config_string_list(sources.get("include", DEFAULT_INCLUDE), "include"),
        "exclude": config_string_list(sources.get("exclude", DEFAULT_EXCLUDE), "exclude"),
        "target_chars": positive_config_int(chunking.get("target_chars", 3000), "target_chars"),
        "max_chars": positive_config_int(chunking.get("max_chars", 4000), "max_chars"),
        "search_limit_default": positive_config_int(output.get("search_limit_default", 5), "search_limit_default"),
        "read_max_chars_default": positive_config_int(output.get("read_max_chars_default", 4000), "read_max_chars_default"),
        "read_max_chars_hard": positive_config_int(output.get("read_max_chars_hard", 12000), "read_max_chars_hard"),
    }
    if result["target_chars"] > result["max_chars"]:
        raise ConfigError("target_chars must be less than or equal to max_chars")
    if result["search_limit_default"] > MAX_RESULT_LIMIT:
        raise ConfigError(f"search_limit_default must be at most {MAX_RESULT_LIMIT}")
    if result["max_chars"] > result["read_max_chars_default"]:
        raise ConfigError("max_chars must be less than or equal to read_max_chars_default")
    if result["read_max_chars_default"] > result["read_max_chars_hard"]:
        raise ConfigError("read_max_chars_default must be less than or equal to read_max_chars_hard")
    return result


def db_path(root: Path, cfg: dict[str, Any] | None = None) -> Path:
    cfg = cfg or config(root)
    p = Path(str(cfg["db_path"]))
    candidate = (p if p.is_absolute() else root.resolve() / p).resolve()
    allowed = context_dir(root)
    try:
        candidate.relative_to(allowed)
    except ValueError as exc:
        raise ConfigError("db_path must stay within .codex-context") from exc
    if candidate.parent != allowed or candidate.suffix not in {".sqlite", ".db"}:
        raise ConfigError("db_path must name a .sqlite or .db file directly inside .codex-context")
    return candidate


def connect(root: Path) -> sqlite3.Connection:
    cfg = config(root)
    path = db_path(root, cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    try:
        con.executescript(FTS_SCHEMA)
        con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('fts5', '1')")
    except sqlite3.OperationalError as exc:
        if not fts_unavailable(exc):
            raise
        con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('fts5', '0')")
    con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', '1')")
    con.commit()
    return con


def ensure_project_files(root: Path) -> None:
    ctx_dir = context_dir(root)
    ctx_dir.mkdir(parents=True, exist_ok=True)
    notes_dir = ctx_dir / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    cfg = ctx_dir / "config.toml"
    if not cfg.exists():
        cfg.write_text(DEFAULT_CONFIG, encoding="utf-8")
    readme = ctx_dir / "README.md"
    if not readme.exists():
        readme.write_text(
            "# Codex Context\n\n"
            "This directory stores the project-local context retrieval system.\n\n"
            "- `ctx.py` searches and reads a SQLite index of Markdown documentation.\n"
            "- `context.sqlite` is generated and should usually stay out of git.\n"
            "- `notes/` can hold extra Markdown notes that should be indexed.\n\n"
            "Common commands:\n\n"
            "```bash\n"
            "python3 .codex-context/ctx.py status\n"
            "python3 .codex-context/ctx.py ingest\n"
            "python3 .codex-context/ctx.py search \"query\" --limit 5\n"
            "python3 .codex-context/ctx.py read <id> --max-chars 4000\n"
            "```\n",
            encoding="utf-8",
        )


def rel_posix(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def is_excluded(rel: str, excludes: Iterable[str]) -> bool:
    parts = rel.split("/")
    for pattern in excludes:
        if fnmatch.fnmatch(rel, pattern):
            return True
        if pattern.endswith("/**"):
            prefix = pattern[:-3]
            if rel == prefix or rel.startswith(prefix + "/"):
                return True
        if any(fnmatch.fnmatch(part, pattern) for part in parts):
            return True
    return False


def discover_sources(root: Path, cfg: dict[str, Any]) -> list[Path]:
    found: dict[str, Path] = {}
    for pattern in cfg["include"]:
        pattern = str(pattern)
        candidates: Iterable[Path]
        if any(ch in pattern for ch in "*?["):
            candidates = root.glob(pattern)
        else:
            candidates = [root / pattern]
        for p in candidates:
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".md", ".mdx"}:
                continue
            try:
                rel = rel_posix(root, p)
            except ValueError:
                continue
            if is_excluded(rel, cfg["exclude"]):
                continue
            found[rel] = p
    return [found[k] for k in sorted(found)]


def file_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def redact_secret_like_content(text: str) -> tuple[str, int]:
    redactions = 0
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted, count = pattern.subn("[REDACTED_SECRET]", redacted)
        redactions += count
    return redacted, redactions


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[`*_~]+", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:80]


def markdown_headings(text: str) -> list[tuple[int, int, int, str]]:
    """Return headings outside fenced code as (start, body_start, level, title)."""
    headings: list[tuple[int, int, int, str]] = []
    fence_char = ""
    fence_len = 0
    offset = 0
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        if fence_char:
            if re.fullmatch(rf" {{0,3}}{re.escape(fence_char)}{{{fence_len},}}[ \t]*", content):
                fence_char = ""
                fence_len = 0
        else:
            fence = re.match(r"^ {0,3}(`{3,}|~{3,})", content)
            if fence:
                fence_char = fence.group(1)[0]
                fence_len = len(fence.group(1))
            else:
                heading = re.match(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", content)
                if heading:
                    headings.append((offset, offset + len(line), len(heading.group(1)), heading.group(2).strip()))
        offset += len(line)
    return headings


def extract_title(path: Path, text: str) -> str:
    for _, _, level, title in markdown_headings(text):
        if level == 1:
            return title
    return path.stem.replace("-", " ").replace("_", " ").strip().title()


def doc_kind(rel: str) -> str:
    if rel == "AGENTS.md":
        return "agents-root"
    if rel.startswith("docs/tasks/"):
        return "task-doc"
    if rel.startswith("docs/agents/") or rel.startswith("agents/"):
        return "agent-doc"
    if rel.startswith(".codex-context/notes/"):
        return "context-note"
    if rel.lower() == "readme.md":
        return "readme"
    return "doc"


def clean_for_summary(text: str, max_chars: int = 520) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"[#>*_\-[\]()]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "…"
    return text


def split_at_line_boundaries(text: str, target: int) -> list[str]:
    parts: list[str] = []
    buffer = ""
    for line in text.splitlines(keepends=True):
        while len(line) > target:
            if buffer:
                parts.append(buffer.rstrip())
                buffer = ""
            parts.append(line[:target].rstrip())
            line = line[target:]
        if buffer and len(buffer) + len(line) > target:
            parts.append(buffer.rstrip())
            buffer = ""
        buffer += line
    if buffer.strip():
        parts.append(buffer.strip())
    return parts


def split_markdown(text: str, cfg: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return (heading, anchor, content) chunks."""
    headings = markdown_headings(text)
    sections: list[tuple[str, str]] = []
    if not headings:
        sections = [("Document", text)]
    else:
        if headings[0][0] > 0:
            preface = text[: headings[0][0]].strip()
            if preface:
                sections.append(("Preface", preface))
        for i, (start, body_start, _, heading) in enumerate(headings):
            end = headings[i + 1][0] if i + 1 < len(headings) else len(text)
            if not text[body_start:end].strip():
                continue
            content = text[start:end].strip()
            sections.append((heading, content))

    target = int(cfg["target_chars"])
    max_chars = int(cfg["max_chars"])
    chunks: list[tuple[str, str, str]] = []
    for heading, content in sections:
        if len(content) <= max_chars:
            chunks.append((heading, slugify(heading), content))
            continue
        parts = split_at_line_boundaries(content, target)
        for part, chunk in enumerate(parts, start=1):
            h = f"{heading} part {part}" if len(parts) > 1 else heading
            chunks.append((h, slugify(h), chunk))
    return chunks


def delete_document(con: sqlite3.Connection, document_id: int) -> None:
    ids = [row[0] for row in con.execute("SELECT id FROM chunks WHERE document_id = ?", (document_id,))]
    for chunk_id in ids:
        try:
            con.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk_id,))
        except sqlite3.OperationalError as exc:
            if not fts_unavailable(exc):
                raise
    con.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
    con.execute("DELETE FROM documents WHERE id = ?", (document_id,))


def ingest_file(con: sqlite3.Connection, root: Path, path: Path, cfg: dict[str, Any], force: bool = False) -> tuple[str, int]:
    rel = rel_posix(root, path)
    raw_text = path.read_text(encoding="utf-8", errors="ignore")
    text, redactions = redact_secret_like_content(raw_text)
    digest = file_hash(raw_text)
    old = con.execute("SELECT id, hash FROM documents WHERE path = ?", (rel,)).fetchone()
    if old and old["hash"] == digest and not force and not redactions:
        count = con.execute("SELECT COUNT(*) FROM chunks WHERE document_id = ?", (old["id"],)).fetchone()[0]
        return "unchanged", int(count)
    if old:
        delete_document(con, int(old["id"]))
    if redactions:
        print(f"warning: redacted {redactions} secret-like value(s) while indexing {rel}", file=sys.stderr)
    title = extract_title(path, text)
    ts = now_iso()
    updated_at = _dt.datetime.fromtimestamp(path.stat().st_mtime, _dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    cur = con.execute(
        "INSERT INTO documents(path, title, kind, hash, updated_at, indexed_at) VALUES (?, ?, ?, ?, ?, ?)",
        (rel, title, doc_kind(rel), digest, updated_at, ts),
    )
    document_id = int(cur.lastrowid)
    chunks = split_markdown(text, cfg)
    for ordinal, (heading, anchor, content) in enumerate(chunks, start=1):
        summary = clean_for_summary(content)
        cur = con.execute(
            """
            INSERT INTO chunks(document_id, path, title, heading, anchor, ordinal, summary, content, tokens_estimate, updated_at, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (document_id, rel, title, heading, anchor, ordinal, summary, content, estimate_tokens(content), updated_at, ts),
        )
        chunk_id = int(cur.lastrowid)
        try:
            con.execute(
                "INSERT INTO chunks_fts(chunk_id, title, path, heading, summary, content) VALUES (?, ?, ?, ?, ?, ?)",
                (chunk_id, title, rel, heading, summary, content),
            )
        except sqlite3.OperationalError as exc:
            if not fts_unavailable(exc):
                raise
    return "indexed", len(chunks)


def cmd_init(args: argparse.Namespace) -> int:
    root = command_root(args.repo)
    ensure_project_files(root)
    with connect(root) as con:
        con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('last_init', ?)", (now_iso(),))
        con.commit()
    print("Initialized context system at .codex-context")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    root = command_root(args.repo)
    ensure_project_files(root)
    cfg = config(root)
    sources = discover_sources(root, cfg)
    with connect(root) as con:
        existing = {row["path"]: row["id"] for row in con.execute("SELECT id, path FROM documents")}
        seen: set[str] = set()
        indexed = unchanged = chunks = 0
        for p in sources:
            rel = rel_posix(root, p)
            seen.add(rel)
            status, count = ingest_file(con, root, p, cfg, force=bool(args.force))
            chunks += count
            if status == "indexed":
                indexed += 1
            else:
                unchanged += 1
        removed = 0
        for rel, document_id in existing.items():
            if rel not in seen:
                delete_document(con, int(document_id))
                removed += 1
        con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('last_ingest', ?)", (now_iso(),))
        con.commit()
    print(f"Indexed {indexed} changed docs, {unchanged} unchanged docs, {removed} removed docs, {chunks} chunks available.")
    return 0


def tokenize_query(query: str) -> list[str]:
    terms = re.findall(r"[A-Za-z0-9_]{2,}", query.lower())
    seen: list[str] = []
    for term in terms:
        if term not in seen:
            seen.append(term)
    return seen


def expand_query_terms(terms: list[str]) -> list[str]:
    expanded: list[str] = []
    for term in terms:
        candidates = [term, *SEMANTIC_ALIASES.get(term, [])]
        for candidate in candidates:
            for token in tokenize_query(candidate):
                if token not in expanded:
                    expanded.append(token)
    return expanded[:18]


def fts_query(terms: list[str], operator: str) -> str:
    clean = [term for term in terms if re.fullmatch(r"[A-Za-z0-9_]{2,}", term)]
    return f" {operator} ".join(f"{term}*" for term in clean[:18])


def row_text(row: sqlite3.Row, key: str) -> str:
    value = row[key]
    return str(value or "").lower()


def term_score(terms: list[str], row: sqlite3.Row, path_weight: int, title_weight: int, body_weight: int) -> int:
    score = 0
    path = row_text(row, "path")
    title = row_text(row, "title")
    heading = row_text(row, "heading")
    summary = row_text(row, "summary")
    content = row_text(row, "content")
    for term in terms:
        if term in path:
            score += path_weight
        if term in title:
            score += title_weight
        if term in heading:
            score += max(title_weight - 4, 1)
        if term in summary:
            score += body_weight * 2
        if term in content:
            score += body_weight
    return score


def rank_search_rows(rows: list[sqlite3.Row], original_terms: list[str], expanded_terms: list[str], limit: int) -> list[sqlite3.Row]:
    semantic_terms = [term for term in expanded_terms if term not in original_terms]

    def key(row: sqlite3.Row) -> tuple[float, float, str, int]:
        score = term_score(original_terms, row, 40, 34, 6)
        score += term_score(semantic_terms, row, 24, 20, 3)
        if row_text(row, "kind") == "agents-root":
            score -= 18
        if row_text(row, "path").startswith("docs/"):
            score += 5
        bm25_score = float(row["score"] or 0)
        return (-score, bm25_score, row_text(row, "path"), int(row["id"]))

    deduped = {int(row["id"]): row for row in rows}
    return sorted(deduped.values(), key=key)[:limit]


def search_rows(con: sqlite3.Connection, query: str, limit: int) -> list[sqlite3.Row]:
    original_terms = tokenize_query(query)[:8]
    expanded_terms = expand_query_terms(original_terms)

    def fetch_fts(match_query: str, candidate_limit: int) -> list[sqlite3.Row]:
        if not match_query:
            return []
        try:
            return list(
                con.execute(
                    """
                    SELECT c.id, c.title, c.path, c.heading, c.summary, c.updated_at, c.tokens_estimate,
                           c.content, d.kind,
                           bm25(chunks_fts) AS score
                    FROM chunks_fts
                    JOIN chunks c ON c.id = chunks_fts.chunk_id
                    JOIN documents d ON d.id = c.document_id
                    WHERE chunks_fts MATCH ?
                    ORDER BY score
                    LIMIT ?
                    """,
                    (match_query, candidate_limit),
                )
            )
        except sqlite3.OperationalError as exc:
            if fts_unavailable(exc):
                return []
            raise

    candidate_limit = max(limit * 8, 30)
    rows: list[sqlite3.Row] = []
    if len(original_terms) > 1:
        rows.extend(fetch_fts(fts_query(original_terms, "AND"), candidate_limit))
    rows.extend(fetch_fts(fts_query(expanded_terms, "OR"), candidate_limit))
    if rows:
        return rank_search_rows(rows, original_terms, expanded_terms, limit)

    words = expanded_terms[:10]
    if not words:
        return []
    clauses = []
    params: list[Any] = []
    for word in words:
        clauses.append("lower(c.title || ' ' || c.path || ' ' || ifnull(c.heading,'') || ' ' || ifnull(c.summary,'') || ' ' || c.content) LIKE ?")
        params.append(f"%{word}%")
    sql = f"""
        SELECT c.id, c.title, c.path, c.heading, c.summary, c.updated_at, c.tokens_estimate,
               c.content, d.kind, 0 AS score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE {' OR '.join(clauses)}
        ORDER BY c.updated_at DESC, c.id ASC
        LIMIT ?
    """
    params.append(candidate_limit)
    return rank_search_rows(list(con.execute(sql, params)), original_terms, expanded_terms, limit)


def row_to_search_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "path": row["path"],
        "heading": row["heading"],
        "summary": row["summary"],
        "updated_at": row["updated_at"],
    }


def cmd_search(args: argparse.Namespace) -> int:
    root = command_root(args.repo)
    cfg = config(root)
    limit = int(args.limit or cfg["search_limit_default"])
    with connect(root) as con:
        rows = search_rows(con, args.query, limit)
    if args.json:
        print(json.dumps([row_to_search_dict(r) for r in rows], indent=2))
        return 0
    if not rows:
        print("No context matches found.")
        return 1
    for row in rows:
        heading = f" — {row['heading']}" if row["heading"] and row["heading"] != row["title"] else ""
        print(f"[{row['id']}] {row['title']}{heading}")
        print(f"path: {row['path']}")
        print(f"updated: {row['updated_at']}")
        print(f"summary: {row['summary']}")
        print()
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    root = command_root(args.repo)
    cfg = config(root)
    max_chars = int(args.max_chars or cfg["read_max_chars_default"])
    max_chars = min(max_chars, int(cfg["read_max_chars_hard"]))
    with connect(root) as con:
        row = con.execute(
            "SELECT id, title, path, heading, anchor, summary, content, updated_at, tokens_estimate FROM chunks WHERE id = ?",
            (int(args.id),),
        ).fetchone()
    if not row:
        print(f"No chunk found for id {args.id}.", file=sys.stderr)
        return 1
    content = row["content"]
    truncated = len(content) > max_chars
    if truncated:
        content = content[: max_chars - 1].rstrip() + "…"
    data = {
        "id": row["id"],
        "title": row["title"],
        "path": row["path"],
        "heading": row["heading"],
        "anchor": row["anchor"],
        "summary": row["summary"],
        "updated_at": row["updated_at"],
        "tokens_estimate": row["tokens_estimate"],
        "truncated": truncated,
        "content": content,
    }
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(f"[{row['id']}] {row['title']} — {row['heading']}")
        print(f"path: {row['path']}#{row['anchor']}")
        print(f"updated: {row['updated_at']} | approx_tokens: {row['tokens_estimate']} | truncated: {str(truncated).lower()}")
        print("\n---\n")
        print(content)
    return 0


def cmd_related(args: argparse.Namespace) -> int:
    root = command_root(args.repo)
    limit = int(args.limit or 5)
    with connect(root) as con:
        src = con.execute("SELECT document_id, ordinal FROM chunks WHERE id = ?", (int(args.id),)).fetchone()
        if not src:
            print(f"No chunk found for id {args.id}.", file=sys.stderr)
            return 1
        rows = list(
            con.execute(
                """
                SELECT id, title, path, heading, summary, updated_at, tokens_estimate,
                       abs(ordinal - ?) AS distance
                FROM chunks
                WHERE document_id = ? AND id != ?
                ORDER BY distance ASC, ordinal ASC
                LIMIT ?
                """,
                (int(src["ordinal"]), int(src["document_id"]), int(args.id), limit),
            )
        )
    if args.json:
        print(json.dumps([row_to_search_dict(r) for r in rows], indent=2))
        return 0
    if not rows:
        print("No related chunks found.")
        return 1
    for row in rows:
        print(f"[{row['id']}] {row['title']} — {row['heading']}")
        print(f"path: {row['path']}")
        print(f"summary: {row['summary']}")
        print()
    return 0


def db_counts(con: sqlite3.Connection) -> dict[str, Any]:
    counts = {
        "documents": con.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
        "chunks": con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
        "fts5": con.execute("SELECT value FROM meta WHERE key = 'fts5'").fetchone(),
        "last_ingest": con.execute("SELECT value FROM meta WHERE key = 'last_ingest'").fetchone(),
    }
    counts["fts5"] = counts["fts5"][0] if counts["fts5"] else "unknown"
    counts["last_ingest"] = counts["last_ingest"][0] if counts["last_ingest"] else None
    return counts


def freshness_counts(root: Path, con: sqlite3.Connection, cfg: dict[str, Any]) -> tuple[int, int, int]:
    sources = discover_sources(root, cfg)
    source_rels = {rel_posix(root, p) for p in sources}
    stale = 0
    for p in sources:
        rel = rel_posix(root, p)
        row = con.execute("SELECT hash FROM documents WHERE path = ?", (rel,)).fetchone()
        text = p.read_text(encoding="utf-8", errors="ignore")
        if not row or row["hash"] != file_hash(text):
            stale += 1
    indexed_rels = {row["path"] for row in con.execute("SELECT path FROM documents")}
    orphaned = len(indexed_rels - source_rels)
    return stale, len(sources), orphaned


def cmd_status(args: argparse.Namespace) -> int:
    root = command_root(args.repo)
    cfg = config(root)
    with connect(root) as con:
        counts = db_counts(con)
        stale, source_total, orphaned = freshness_counts(root, con, cfg)
    data = {
        "repo": ".",
        "db_path": rel_posix(root, db_path(root, cfg)),
        "documents": counts["documents"],
        "chunks": counts["chunks"],
        "source_files": source_total,
        "stale_or_missing_sources": stale,
        "orphaned_indexed_documents": orphaned,
        "fts5": counts["fts5"],
        "last_ingest": counts["last_ingest"],
    }
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        for key, value in data.items():
            print(f"{key}: {value}")
        if stale or orphaned:
            print("status: stale; run `python3 .codex-context/ctx.py ingest`")
        else:
            print("status: fresh")
    return 0 if not stale and not orphaned else 2


def cmd_recent(args: argparse.Namespace) -> int:
    root = command_root(args.repo)
    limit = int(args.limit or 10)
    with connect(root) as con:
        rows = list(
            con.execute(
                """
                SELECT id, title, path, heading, summary, updated_at, tokens_estimate
                FROM chunks
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            )
        )
    if args.json:
        print(json.dumps([row_to_search_dict(r) for r in rows], indent=2))
        return 0
    for row in rows:
        print(f"[{row['id']}] {row['title']} — {row['heading']}")
        print(f"path: {row['path']} | updated: {row['updated_at']}")
        print(f"summary: {row['summary']}")
        print()
    return 0


def cmd_rebuild(args: argparse.Namespace) -> int:
    root = command_root(args.repo)
    cfg = config(root)
    path = db_path(root, cfg)
    if path.exists():
        path.unlink()
    ensure_project_files(root)
    with connect(root):
        pass
    args.force = True
    return cmd_ingest(args)


def cmd_doctor(args: argparse.Namespace) -> int:
    root = command_root(args.repo)
    cfg = config(root)
    problems: list[str] = []
    agents = root / "AGENTS.md"
    if not agents.exists():
        problems.append("AGENTS.md missing")
    else:
        text = agents.read_text(encoding="utf-8", errors="ignore")
        if text.count("project-context:start") != 1 or text.count("project-context:end") != 1:
            problems.append("AGENTS.md should contain exactly one marked project-context section")
    if not (root / ".codex-context" / "config.toml").exists():
        problems.append("missing .codex-context/config.toml")
    if not (root / ".codex-context" / "ctx.py").exists():
        problems.append("missing .codex-context/ctx.py")
    if not (root / "docs" / "agents" / "context.md").exists():
        problems.append("missing docs/agents/context.md")
    with connect(root) as con:
        counts = db_counts(con)
        stale, source_total, orphaned = freshness_counts(root, con, cfg)
    print("repo: .")
    print(f"db: {rel_posix(root, db_path(root, cfg))}")
    print(f"documents: {counts['documents']} | chunks: {counts['chunks']} | source_files: {source_total}")
    print(f"fts5: {counts['fts5']} | last_ingest: {counts['last_ingest']}")
    if stale:
        problems.append(f"{stale} source files are stale or missing from index")
    if orphaned:
        problems.append(f"{orphaned} indexed documents no longer match configured sources")
    if problems:
        print("problems:")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print("doctor: ok")
    return 0


def positive_cli_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def result_limit(value: str) -> int:
    parsed = positive_cli_int(value)
    if parsed > MAX_RESULT_LIMIT:
        raise argparse.ArgumentTypeError(f"value must be at most {MAX_RESULT_LIMIT}")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SQLite-backed project context search for Codex")
    parser.add_argument("--repo", help="Repository root. Defaults to auto-detected root.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="Create context directories, config, and database schema")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("ingest", help="Index configured Markdown files into SQLite")
    p.add_argument("--force", action="store_true", help="Re-index unchanged files")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("rebuild", help="Delete and rebuild the SQLite index")
    p.set_defaults(func=cmd_rebuild)

    p = sub.add_parser("search", help="Search indexed context")
    p.add_argument("query")
    p.add_argument("--limit", type=result_limit)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("read", help="Read one chunk by ID")
    p.add_argument("id", type=int)
    p.add_argument("--max-chars", type=positive_cli_int)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_read)

    p = sub.add_parser("related", help="Show nearby chunks from the same document")
    p.add_argument("id", type=int)
    p.add_argument("--limit", type=result_limit)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_related)

    p = sub.add_parser("recent", help="Show recently updated chunks")
    p.add_argument("--limit", type=result_limit)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_recent)

    p = sub.add_parser("status", help="Show index status and freshness")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("doctor", help="Validate context setup")
    p.set_defaults(func=cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
