# Risk-Routed Subagent Orchestration

Purpose: Route repository work to the smallest safe Codex workflow.
Read when: classifying, delegating, escalating, or reviewing standard and
critical work.
Do not read for: small local tasks that the primary agent can complete
sequentially.
Source of truth: `.codex/config.toml`, `.codex/agents/*.toml`, the root
`AGENTS.md`, and this guide.
Last reviewed: 2026-07-30

## Summary

- Keep small sequential work with the primary agent.
- Route standard and critical work by risk score through bounded contracts.
- Use one writer by default and preserve human approval gates.

## Operating Rules

The primary agent remains user-selected. It classifies the task, delegates
bounded work, integrates results, and owns final verification. Project
configuration controls only spawned agents.

Use at most three concurrent subagents. Read-only work may run in parallel.
Use one writer by default. A second writer is allowed only in an isolated
worktree with non-overlapping files and pre-agreed interfaces.

All agents must preserve the pack, security, distribution, and verification
rules in the root `AGENTS.md`.

Profile sandbox modes are defaults. Live parent sandbox and permission overrides
supersede them and are inherited by spawned agents.

## Score Risk Before Delegating

Add the points for every applicable condition:

| Condition | Points |
| --- | ---: |
| More than five files, weak tests, or an unfamiliar subsystem | +1 |
| Crosses runtime, frontend, workflow, packaging, or CI boundaries | +2 |
| Changes tensor batch/device/dtype behavior or persisted workflow contracts | +2 |
| Requirements are materially ambiguous | +2 |
| Adds filesystem, network, archive, route, credential, or concurrency behavior | +3 |
| Changes registration IDs, compatibility floors, release, or publication | +3 |

Route the total:

- `0-2` — Small: the primary agent works directly. Do not spawn subagents.
- `3-5` — Standard: use `planner`, then `worker`, then `qa`. Add `reviewer`
  only if a critical boundary remains.
- `6+` — Critical: use `planner`; obtain required human approval; use
  `critical_worker` for the difficult core; add bounded `explorer`, `worker`,
  or `qa` support only for independent work; finish with `qa` and `reviewer`.

## Delegation Contract

Every delegated task must state:

- objective and non-goals;
- acceptance criteria;
- owned, read-only, and forbidden files;
- existing patterns and interfaces to preserve;
- required checks and allowed commands;
- network and secret access;
- retry limit and stop conditions; and
- expected return format.

Every subagent must return:

- status;
- files inspected and changed;
- implementation or findings;
- checks run with exact results;
- assumptions;
- residual risks; and
- recommended next action.

Reject an incomplete handoff. The primary agent verifies integrated work rather
than relying on a subagent's completion claim.

## Escalate Terra To Sol

Stop Terra work and escalate to Sol when:

- the same check fails after two materially different fixes;
- work crosses an unplanned subsystem or assigned file boundary;
- the approved architecture or a persisted workflow contract must change;
- filesystem, route, release, security, concurrency, or compatibility risk
  appears unexpectedly;
- the root cause lacks file-level evidence; or
- two repair rounds do not resolve the same review finding.

## Bounded Sol Review

Use `reviewer` only for a high-risk integrated diff or when a standard workflow
leaves a critical boundary. Review only for correctness, security, data loss,
regression, contracts, critical error handling, material performance,
maintainability, and important test gaps.

Every finding must include severity, location, concrete failure path, evidence,
impact, and the smallest correction. Exclude style-only and unrelated findings.

## Human Gates

Do not delegate or infer human approval. Stop for explicit approval before
changing public workflow contracts, taking destructive actions, changing
registration IDs or compatibility floors, or starting release or publication.

Publishing additionally requires an explicitly approved release, the complete
qualification workflow, a protected Registry token, and the tag and environment
controls documented in `README.md`. Published names and versions are immutable.

## Configuration Gate

Run `codex doctor --json` after changing project agent configuration or
instructions. Project-agent loading failures block completion; unrelated global
warnings must be reported separately.
