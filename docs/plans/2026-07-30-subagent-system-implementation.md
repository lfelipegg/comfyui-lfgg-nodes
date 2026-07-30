# Risk-Routed Codex Subagent System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a project-scoped Sol/Terra custom-agent system with risk routing,
bounded delegation, and a persistent configuration check.

**Architecture:** Keep the primary model user-selected. Configure spawned agents
under `.codex/`, put operational routing in `agents/orchestrator.md`, and keep
only a short durable pointer in `AGENTS.md`.

**Tech Stack:** Codex TOML configuration, Markdown, Python standard-library TOML
parsing, pytest.

---

### Task 1: Lock The Custom-Agent Contract

**Files:**

- Create: `tests/unit/test_codex_agents.py`
- Create: `.codex/config.toml`
- Create: `.codex/agents/planner.toml`
- Create: `.codex/agents/explorer.toml`
- Create: `.codex/agents/worker.toml`
- Create: `.codex/agents/qa.toml`
- Create: `.codex/agents/critical_worker.toml`
- Create: `.codex/agents/reviewer.toml`

**Step 1: Write the failing test**

Parse `.codex/config.toml` and every `.codex/agents/*.toml`. Assert:

- the concurrency cap is `3`;
- unspecified spawned agents default to Terra Medium;
- exactly the six approved agent names exist;
- every profile has non-empty `name`, `description`, and
  `developer_instructions`;
- models are `gpt-5.6-sol` or `gpt-5.6-terra`;
- efforts are `medium`, `high`, or `xhigh`;
- sandboxes are `read-only` or `workspace-write`; and
- planner, explorer, and reviewer are read-only.

**Step 2: Run the test to verify it fails**

Run:

```bash
python -m pytest -q tests/unit/test_codex_agents.py
```

Expected: fail because `.codex/config.toml` and the profiles do not exist.

**Step 3: Add the minimum configuration**

Create `.codex/config.toml`:

```toml
[agents]
enabled = true
max_concurrent_threads_per_session = 3
default_subagent_model = "gpt-5.6-terra"
default_subagent_reasoning_effort = "medium"
```

Create six standalone profiles with required metadata and narrow instructions:

- `planner`: Sol High, read-only planning with acceptance criteria and risks.
- `explorer`: Terra Medium, read-only execution-path evidence.
- `worker`: Terra High, one bounded writer using project patterns and checks.
- `qa`: Terra High, workspace-write for checks and explicitly approved fixes.
- `critical_worker`: Sol XHigh, narrow difficult-core implementation.
- `reviewer`: Sol High, read-only high-risk findings without style noise.

Each profile must require the structured return fields from the approved
design and must stop when its scope or risk boundary is exceeded.

**Step 4: Run the test to verify it passes**

Run:

```bash
python -m pytest -q tests/unit/test_codex_agents.py
```

Expected: one passing test.

### Task 2: Add Project Routing

**Files:**

- Create: `agents/orchestrator.md`
- Modify: `AGENTS.md`

**Step 1: Write the operational orchestrator guide**

Add the project risk score, small/standard/critical workflows, single-writer
default, delegation and return contracts, Terra-to-Sol escalation conditions,
bounded Sol review contract, and existing human release/public-contract gates.

Do not duplicate node implementation rules from `AGENTS.md`.

**Step 2: Correct stale root instructions**

Replace the “future pack/research only” description with the implemented
successor-pack state and point to `README.md` and `pyproject.toml` for the
current node and compatibility contract.

Remove the resolved `Assumptions to Confirm` section. Add a compact subagent
routing section that:

- forbids delegation for small sequential tasks;
- requires `agents/orchestrator.md` for standard or critical work;
- defaults to one writer; and
- names `.codex/agents/` as the profile source.

**Step 3: Check documentation shape**

Run:

```bash
wc -l AGENTS.md
rg -n "\[[^]]+\]|TODO|TBD" AGENTS.md agents .codex
test -f agents/orchestrator.md
```

Expected: `AGENTS.md` is at most 200 lines, no placeholders are found, and the
orchestrator guide exists.

### Task 3: Verify And Index

**Files:**

- Update generated, ignored index: `.codex-context/context.sqlite`

**Step 1: Run focused static and unit checks**

Run:

```bash
python -m ruff check tests/unit/test_codex_agents.py
python -m pytest -q tests/unit/test_codex_agents.py
git diff --check
```

Expected: all commands pass.

**Step 2: Refresh project context**

Run:

```bash
python3 .codex-context/ctx.py ingest
python3 .codex-context/ctx.py doctor
python3 .codex-context/ctx.py search "risk routed subagent" --limit 3
```

Expected: ingest succeeds, the index is healthy, and the new orchestrator or
design documentation is returned.

**Step 3: Review final scope**

Run:

```bash
git status --short
git diff --stat
git diff -- AGENTS.md agents .codex tests/unit/test_codex_agents.py
```

Expected: only the approved agent-system files are changed; the user's
untracked `.vscode/` directory remains untouched.
