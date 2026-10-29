# Claude Code guidance

`AGENTS.md` is the single source of truth for this repository and is shared with
Oh My Pi (`.omp/AGENTS.md`) and Codex. Edit guidance there, not here; this file
only imports it and maps agent-specific tool names for Claude Code.

@AGENTS.md

## Claude Code tool mapping

- Where `AGENTS.md` says to use OMP's interactive `ask` tool, use
  `AskUserQuestion` with the same rules: batch independent questions (up to four
  per call), mark recommended options with "(Recommended)" as the first option,
  and defer dependent questions until their prerequisites are answered.
- Apply `docs/agents/orchestration.md` to the `Agent` tool. Map OMP's `scout` to
  `Explore`, `task` to `general-purpose`, and `reviewer`/`security-reviewer` to
  the `code-review` or `security-review` skills or a read-only
  `general-purpose` agent with the review contract. Keep the same limits: at
  most three concurrent subagents, one writer (`isolation: "worktree"` for an
  approved second writer), no nested delegation, and final verification in the
  primary agent. `.omp/config.yml` and `.codex/agents/` do not configure Claude
  Code; do not duplicate them as `.claude/agents/`.
- `$project-context` means the user-level `project-context` skill; invoke it
  through the `Skill` tool. If it is unavailable, run the
  `.codex-context/ctx.py` commands directly.
- User-level skills come from `~/.claude/skills`, which links the shared skills
  in `~/.agents/skills` and `~/.codex/skills`. Invoke them with the `Skill`
  tool rather than reading their files by hand.
