# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues. Use the `gh` CLI for all
operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`.
- **Read an issue**: `gh issue view <number> --comments`, including labels.
- **List issues**: `gh issue list --state open` with appropriate label and
  state filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`.
- **Apply or remove labels**: `gh issue edit <number> --add-label "..."` or
  `--remove-label "..."`.
- **Close an issue**: `gh issue close <number> --comment "..."`.

Infer the repository from `git remote -v`; `gh` does this automatically inside
the clone.

## Pull requests as a triage surface

**PRs as a request surface: no.**

GitHub shares one number space across issues and pull requests. Resolve an
ambiguous number with `gh pr view <number>` and fall back to
`gh issue view <number>`.

## Skill operations

- When a skill says **publish to the issue tracker**, create a GitHub issue.
- When a skill says **fetch the relevant ticket**, run
  `gh issue view <number> --comments`.

## Wayfinding operations

The map is one issue with child issues as tickets.

- **Map**: create one issue labelled `wayfinder:map`.
- **Child ticket**: link an issue to the map as a GitHub sub-issue. If
  sub-issues are unavailable, add it to a task list in the map and put
  `Part of #<map>` at the top of the child body.
- **Ticket labels**: use `wayfinder:research`, `wayfinder:prototype`,
  `wayfinder:grilling`, or `wayfinder:task`.
- **Blocking**: use GitHub's native issue dependencies. Add an edge with
  `gh api --method POST
  repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by
  -F issue_id=<blocker-database-id>`. The database ID comes from
  `gh api repos/<owner>/<repo>/issues/<number> --jq .id`.
- **Dependency fallback**: if native dependencies are unavailable, put
  `Blocked by: #<number>` at the top of the child body.
- **Frontier**: the map's open, unblocked, unassigned children, in map order.
- **Claim**: `gh issue edit <number> --add-assignee @me` before doing work.
- **Resolve**: comment with the answer, close the ticket, then append a
  one-line gist and link to the map's Decisions-so-far.
