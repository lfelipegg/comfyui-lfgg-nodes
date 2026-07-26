# Domain Docs

How engineering skills consume this repository's domain documentation.

## Before exploring

- Read the root `CONTEXT.md`.
- Read ADRs under `docs/adr/` that affect the area being explored.
- If either location is absent, proceed silently. Domain-modeling creates
  glossary and decision files only when the first relevant item is resolved.

## Layout

This is a single-context repository:

```text
/
├── CONTEXT.md
├── docs/adr/
└── src/
```

## Vocabulary

Use the canonical terms from `CONTEXT.md` in issues, plans, tests, and code.
Avoid listed synonyms. If a needed domain concept is missing, reconsider the
term or raise it during domain modeling.

## ADR conflicts

Surface any conflict with an existing ADR instead of silently overriding it.
