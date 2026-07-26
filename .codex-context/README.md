# Codex Context

Purpose: project-local SQLite-backed context retrieval for Codex.

The Markdown files remain the source of truth. The SQLite database is a generated index used to search first and read only bounded chunks by ID.

## Commands

```bash
python3 .codex-context/ctx.py status
python3 .codex-context/ctx.py ingest
python3 .codex-context/ctx.py search "query" --limit 5
python3 .codex-context/ctx.py read <id> --max-chars 4000
python3 .codex-context/ctx.py related <id> --limit 5
python3 .codex-context/ctx.py doctor
python3 .codex-context/test_ctx.py
```

## Files

- `ctx.py`: project-local context CLI.
- `test_ctx.py`: focused checks for chunking and trust boundaries.
- `config.toml`: include/exclude patterns and limits.
- `context.sqlite`: generated index; usually keep out of git.
- `notes/`: optional Markdown notes to index.

## Token Discipline

Search first. Read only directly relevant IDs. Do not dump whole tables or large
docs. `AGENTS.md` is not indexed because agents receive it separately.

The database path must stay inside `.codex-context/`, and generated indexes stay
out of git.

## Compatibility

The CLI supports Python 3.9+. On Python 3.11+, it uses `tomllib` for config parsing. On Python 3.9 and 3.10, it uses a small built-in parser for this generated config shape.
