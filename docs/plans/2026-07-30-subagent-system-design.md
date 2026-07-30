# Risk-Routed Codex Subagent System Design

Purpose: Define the project-scoped Codex agents and routing rules used to match
GPT-5.6 Sol and Terra to LFGG Nodes work.
Read when: creating, changing, or operating this repository's subagent system.
Do not read for: ordinary implementation tasks after the routing rules have
selected a workflow.
Source of truth: `.codex/config.toml`, `.codex/agents/*.toml`,
`agents/orchestrator.md`, and the root `AGENTS.md`.
Last reviewed: 2026-07-30

## Summary

- Keep the primary model user-selected; project configuration controls only
  spawned agents.
- Use no subagents for small local work, Terra for bounded exploration,
  implementation, and QA, and Sol for planning, critical implementation, and
  high-risk review.
- Default to one writer and at most three concurrent subagents.
- Escalate after repeated failed fixes, unexplained root cause, scope growth, or
  discovery of a critical project boundary.

## Architecture

The root agent is the deterministic workflow controller. It classifies the task,
selects the smallest workflow that can safely complete it, gives each subagent a
bounded contract, integrates results, and owns final verification.

Project-scoped custom agents live in `.codex/agents/`:

| Profile | Model | Effort | Sandbox | Responsibility |
| --- | --- | --- | --- | --- |
| `planner` | Sol | high | read-only | Plan standard and critical work |
| `explorer` | Terra | medium | read-only | Trace unfamiliar code paths |
| `worker` | Terra | high | workspace-write | Implement bounded changes |
| `qa` | Terra | high | workspace-write | Run checks and diagnose failures |
| `critical_worker` | Sol | xhigh | workspace-write | Implement difficult critical cores |
| `reviewer` | Sol | high | read-only | Review high-risk integrated diffs |

No project default is set for the primary model. Unspecified spawned agents
default to Terra Medium. The concurrent subagent cap is three.

## Risk Routing

Score the expected work before delegation:

| Condition | Points |
| --- | ---: |
| More than five files, weak tests, or an unfamiliar subsystem | +1 |
| Crosses runtime, frontend, workflow, packaging, or CI boundaries | +2 |
| Changes tensor batch/device/dtype behavior or persisted workflow contracts | +2 |
| Requirements are materially ambiguous | +2 |
| Adds filesystem, network, archive, route, credential, or concurrency behavior | +3 |
| Changes registration IDs, compatibility floors, release, or publication | +3 |

Route by total:

- `0-2`: the primary agent works directly; do not spawn subagents.
- `3-5`: Sol planner, Terra worker, then Terra QA. Add Sol review only if a
  critical boundary remains.
- `6+`: Sol planner, an approval gate when public contracts, destructive
  actions, release, or publication are involved, Sol critical worker for the
  difficult core, bounded Terra support when independent, Terra QA, and
  independent Sol review.

Use read parallelism freely within the three-thread cap. Use one writer by
default. A second writer is allowed only in an isolated worktree with
non-overlapping files and pre-agreed interfaces.

## Delegation Contract

Every delegated task states:

- objective and non-goals;
- acceptance criteria;
- owned, read-only, and forbidden files;
- existing patterns and interfaces to preserve;
- required checks and allowed commands;
- network and secret access;
- retry limit and stop conditions;
- expected return format.

Every subagent returns status, files inspected and changed, implementation or
findings, checks run with exact results, assumptions, residual risks, and the
recommended next action. The root agent rejects incomplete handoffs.

## Escalation And Review

Stop Terra and escalate to Sol when:

- the same check fails after two materially different fixes;
- the work crosses an unplanned subsystem or assigned file boundary;
- the approved architecture or a persisted workflow contract must change;
- filesystem, route, release, security, concurrency, or compatibility risk
  appears unexpectedly;
- the root cause cannot be supported with file-level evidence; or
- two repair rounds do not resolve the same review finding.

The Sol reviewer reports only correctness, security, data-loss, regression,
contract, critical error-handling, material performance, maintainability, or
important test gaps. Each finding includes severity, location, concrete failure
path, evidence, impact, and the smallest correction. Style-only and unrelated
findings are excluded.

## Verification

The implementation must:

- parse every new TOML file;
- confirm every custom agent has `name`, `description`, and
  `developer_instructions`;
- confirm only supported project model names and reasoning levels are used;
- keep root `AGENTS.md` below 200 lines;
- leave no placeholders;
- resolve every referenced agent path; and
- ingest and check the project context index after Markdown changes.

## Deliberate Omissions

- No Luna profile: this Codex environment exposes only GPT-5.6 Sol and Terra.
- No permanent utility, integrator, or routine reviewer: create those roles
  only when a real task needs them.
- No metrics ledger or custom workflow controller: add automation only after
  repeated routing mistakes show that written rules and Codex configuration are
  insufficient.
