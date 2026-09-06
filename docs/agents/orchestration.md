# OMP-First Agent Orchestration

Purpose: Delegate only work that benefits from independent context or genuine
parallelism while keeping the primary agent responsible for the result.
Read when: deciding whether or how to use subagents.
Do not read for: small or sequential work that stays in the primary agent.
Source of truth: `.omp/config.yml`, the root `AGENTS.md`, and this guide.
Last reviewed: 2026-09-05

## Operating Model

- The primary agent interprets the request, decomposes it, integrates all
  results, and runs final verification.
- Do not delegate small tasks, top-level planning, or work whose next step
  depends on the previous one.
- Use no more than three concurrent subagents. Read-only work may fan out; use
  one writer by default.
- A second writer is allowed only for non-overlapping files in isolated
  workspaces with interfaces agreed before spawning.
- Project task agents may not spawn children. Coordination stays with the
  primary agent.

OMP supplies the project roster:

| Agent | Use |
| --- | --- |
| `sonic` | Strictly mechanical edits or bounded data collection |
| `scout` | Read-only exploration, path tracing, and repository facts |
| `task` | One bounded implementation slice |
| `reviewer` | Material correctness review of an integrated change |
| `security-reviewer` | Evidence-backed review of a security-sensitive change |

The project does not override these agents. `.omp/config.yml` routes them
through role aliases so user-level model choices remain portable.

## Delegation Gate

Before spawning:

1. Resolve repository facts available through files, context, or tools.
2. Decompose the request in the primary agent.
3. Identify independent slices and their shared interfaces.
4. Keep coupled edits with one owner; overlapping writers are prohibited.
5. Use one batch for independent siblings rather than serial task calls.

Delegate only when a slice is independently runnable and benefits from separate
context, specialist review, or real parallelism. A generic planning agent starts
with less context than the primary agent and is not a substitute for
decomposition.

## Delegation Contract

Shared batch context must state:

- the overall goal;
- repository and task constraints; and
- interfaces or formats shared across slices.

Each task must state:

- exact target files or subsystem and explicit non-goals;
- the complete change or investigation;
- observable acceptance criteria;
- editable, read-only, and forbidden areas;
- patterns and contracts to preserve;
- allowed tools, network or secret access, and stop conditions; and
- the required return format.

Concurrent agents must skip formatters, linters, and project-wide tests. The
primary agent runs relevant verification once after integration.

## Coordination And Handoff

- Subagents begin without the parent conversation. Include all slice-specific
  requirements in their contract.
- Use `hub` messages for follow-up or cross-slice coordination. Do not poll
  background jobs while useful primary work remains.
- Reject incomplete handoffs. A useful result names files inspected and changed,
  findings or implementation, checks actually run, assumptions, residual risks,
  and the next action.
- Treat a subagent's completion claim as evidence to inspect, not final
  verification.

## Review And Escalation

Use `reviewer` only for an integrated change with material correctness,
data-loss, regression, contract, error-handling, performance, or maintainability
risk. Use `security-reviewer` when work adds or changes filesystem, network,
archive, route, credential, authorization, or untrusted-input behavior.

Every finding must include severity, location, concrete failure path, evidence,
impact, and the smallest correction. Exclude style-only and unrelated findings.

Stop and reassess when:

- the same check fails after two materially different fixes;
- work crosses an unplanned subsystem or ownership boundary;
- a persisted workflow contract or approved architecture must change;
- security, release, concurrency, or compatibility risk appears unexpectedly;
  or
- the root cause lacks file-level evidence.

## Human Gates

Obtain explicit user approval before destructive actions, public workflow
contract changes, registration-ID or compatibility-floor changes, release, or
publication. Do not infer approval from a delegated task.

Publishing additionally requires the complete qualification workflow, protected
Registry credentials and environment, and the tag controls in `README.md`.
Published names and versions are immutable.

## Secondary Codex Compatibility

Codex may use `.codex/agents/explorer.toml`, `worker.toml`, and `reviewer.toml`.
They provide research, bounded writing, and review only; they do not recreate an
automatic planner-worker-QA pipeline. The primary agent still plans, integrates,
and verifies.

## Configuration Verification

After changing agent configuration or guidance:

- run `python -m pytest -q tests/unit/test_agent_configuration.py`;
- exercise one bundled OMP subagent from a fresh repository-root session and
  inspect its resolved agent and model metadata;
- run `codex doctor --json` when `.codex/` compatibility files change; and
- ingest and check project context after meaningful Markdown changes.

Configuration parsing alone does not prove runtime discovery.
