# Token-Efficient Documentation Guide

Purpose: help Codex retrieve only the context it needs.
Read when: creating or reorganizing documentation for agent use.
Do not read for: trivial source edits that already have all needed context.
Source of truth: repository source files and current project commands.
Last reviewed: 2026-07-26

## Summary

- Keep `AGENTS.md` short and operational.
- Put detailed but durable guidance in focused Markdown files.
- Index Markdown into SQLite for bounded search and read-by-ID retrieval.
- Use summaries, stable headings, and dates so Codex can decide what to read.
- Treat SQLite as a generated index unless the user explicitly chooses DB-only notes.

## Recommended Markdown Shape

Start substantial docs with:

```md
# Title

Purpose: one or two sentences.
Read when: specific tasks or questions.
Do not read for: cases where this file is unnecessary.
Source of truth: files, services, or commands that supersede this document.
Last reviewed: YYYY-MM-DD

## Summary

- Short fact or rule.
- Short fact or rule.
- Short fact or rule.
```

Then use stable headings and one topic per section.

## What Belongs In AGENTS.md

- commands
- guardrails
- repo workflow
- when to use support docs
- when to use `$project-context`
- final response expectations

## What Belongs Outside AGENTS.md

- architecture history
- migration notes
- deployment details
- API references
- task logs
- long examples
- troubleshooting catalogs
- generated reports

## What To Index

Index these by default:

- `README.md`
- `docs/**/*.md`
- `docs/**/*.mdx`
- `agents/**/*.md`
- `.codex-context/notes/**/*.md`

`AGENTS.md` is already supplied to agents, so indexing it duplicates results.
Do not index `reference/**`, secrets, dependencies, build or coverage output, or
local environment files.
