# Sizing 1.0.0 Release Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the three-node sizing family and make its exact `1.0.0`
archive ready for protected Registry publication.

**Architecture:** One standard-library fitter owns aligned-dimension selection.
Three thin V1 adapters supply either an explicit ratio or tensor-derived
constraints. Package and integration tests exercise `node.zip`; two GitHub
workflows separate untrusted verification from approved publication.

**Tech Stack:** Python 3.10–3.13, Torch supplied by ComfyUI, pytest, Ruff,
comfy-cli, `zipfile`, GitHub Actions.

---

### Task 1: Generalize the sizing fitter

**Files:**
- Modify: `tests/unit/test_sizing.py`
- Modify: `lfgg_nodes/sizing.py`

**Step 1: Write the failing source-dimension tests**

Add focused tests for a pure helper with this contract:

```python
fit_source_dimensions(
    source_width=1920,
    source_height=1080,
    max_width=1024,
    max_height=576,
    max_pixels=None,
    divisible_by=64,
    max_resolution=16_384,
) == (1024, 576)
```

Cover reciprocal orientation, already-small sources, a coarse-alignment case
where aspect fidelity beats area, an exact pixel ceiling, impossible
alignment, and invalid integer bounds.

**Step 2: Verify RED**

Run:
`python -m pytest -q tests/unit/test_sizing.py -k source`

Expected: failure because `fit_source_dimensions` does not exist.

**Step 3: Implement the minimum shared fitter**

Enumerate aligned candidates within the independent axis ceilings. Compare
candidate/source aspect ratios using the existing integer symmetric error,
then area, long side, and short side. Reject `bool`, non-integer, nonpositive,
over-`MAX_RESOLUTION`, over-budget, and impossible constraints.

Refactor `fit_aspect_ratio_dimensions` to call the shared fitter with equal
axis ceilings. Keep the public result and preset behavior unchanged.

**Step 4: Verify GREEN**

Run:
`python -m pytest -q tests/unit/test_sizing.py`

Expected: all sizing tests pass.

**Step 5: Commit**

```bash
git add tests/unit/test_sizing.py lfgg_nodes/sizing.py
git commit -m "feat: share aligned sizing fitter"
```

### Task 2: Add the two image-derived sizing nodes

**Files:**
- Create: `lfgg_nodes/image_dimensions.py`
- Modify: `tests/unit/test_contract.py`
- Create: `tests/unit/test_image_dimensions.py`
- Modify: `__init__.py`

**Step 1: Write failing schema and tensor tests**

Assert exact V1 registration for:

```python
{
    "LFGG_DimensionsByAspectRatio",
    "LFGG_ImageDimensionsByLongSide",
    "LFGG_ImageDimensionsByPixelBudget",
}
```

Use real CPU Torch tensors shaped `[B,H,W,C]`. Cover long-side downscale and
already-small branches, pixel-budget downscale and already-small branches,
batches, coarse alignment, invalid tensor type/rank/zero axes, invalid API
bounds, impossible alignment, and exact preservation of tensor identity,
shape, values, dtype, and device. Mark a CUDA identity test to skip unless CUDA
is available.

**Step 2: Verify RED**

Run:
`python -m pytest -q tests/unit/test_contract.py tests/unit/test_image_dimensions.py`

Expected: failures because the nodes and registrations are absent.

**Step 3: Implement thin adapters**

Create both classes in one module. Lazily import Torch only while validating
execution input. Read `[B,H,W,C]`, reject nonpositive axes, and pass the source
width/height plus the accepted constraints to the pure fitter.

Long-side caps use exact integer arithmetic equivalent to:

```python
scale = min(1, long_side / max(source_width, source_height))
```

Pixel-budget fitting keeps source axis ceilings and applies the exact integer
`max_pixels` ceiling. Neither adapter touches tensor storage.

Register the two IDs and display names through the existing duplicate-rejecting
merge helper.

**Step 4: Verify GREEN**

Run:
`python -m pytest -q tests/unit/test_contract.py tests/unit/test_image_dimensions.py`

Expected: all selected tests pass, with CUDA skipped when unavailable.

**Step 5: Commit**

```bash
git add __init__.py lfgg_nodes/image_dimensions.py tests/unit
git commit -m "feat: complete sizing node family"
```

### Task 3: Synchronize schemas, workflow, and migration guidance

**Files:**
- Create: `release/1.0.0-schema.json`
- Replace: `workflows/dimensions_by_aspect_ratio.json`
- Create: `workflows/sizing.json`
- Modify: `tests/unit/test_contract.py`
- Modify: `README.md`

**Step 1: Write failing synchronization assertions**

Assert that the release schema manifest exactly matches all three registered
IDs, display names, categories, input order/types/defaults/bounds, output
types/names, and descriptions.

Assert `workflows/sizing.json` exercises all three nodes and connects every
dimension pair to a native latent initializer. Use a small generated native
image source for the image-derived nodes so no model or external asset is
required.

Assert README migration text covers:

- all three sizing predecessors;
- native `ImageFromBatch` replacing `LfggImageBatchSelect`;
- an explicit label replacing `LfggModelNameFromModel`; and
- deferred Prompt Library, Prompt Wildcard, and LoRA-by-path families.

**Step 2: Verify RED**

Run:
`python -m pytest -q tests/unit/test_contract.py`

Expected: failure because the manifest, complete workflow, and migration text
are absent.

**Step 3: Add the minimum synchronized artifacts**

Replace the one-node workflow with one complete sizing workflow and remove the
obsolete filename. Keep the manifest as plain JSON so both pytest and the
integration harness can consume it without a dependency.

**Step 4: Verify GREEN**

Run:
`python -m pytest -q tests/unit/test_contract.py`

Expected: pass.

**Step 5: Commit**

```bash
git add README.md release/1.0.0-schema.json workflows tests/unit/test_contract.py
git commit -m "docs: complete sizing release contract"
```

### Task 4: Inspect the exact Registry archive

**Files:**
- Create: `.comfyignore`
- Create: `tests/package/conftest.py`
- Create: `tests/package/test_archive.py`
- Create: `release/1.0.0-archive.sha256`
- Modify: `pyproject.toml`

**Step 1: Write failing archive-security tests**

Tests receive `--archive`, defaulting to `node.zip`. Add unit-sized temporary
ZIP cases for absolute paths, `..`, backslash traversal, duplicate normalized
members, symlink entries, forbidden development/private names, and oversized
members.

For the real archive, assert the exact distributable file set and sorted
`sha256  relative/path` lines equal the approved release manifest.

**Step 2: Verify RED**

Run:
`python -m pytest -q tests/package`

Expected: a clear missing-archive failure until the candidate is packed.

**Step 3: Implement inspection with the standard library**

Use `zipfile`, `pathlib.PurePosixPath`, and `hashlib.sha256`. Inspect all
members before extracting anything. Bound member count and uncompressed bytes,
reject unsafe modes and duplicate normalized paths, then extract only into a
temporary directory and prove containment.

Configure `.comfyignore` to exclude `.git*`, `.github`, `.codex*`, `AGENTS.md`,
`CONTEXT.md`, `docs`, `reference`, `release`, tests, caches, coverage, build
outputs, and local archives. Include only runtime code, metadata, license,
README, and the sizing workflow.

**Step 4: Pack and approve the manifest**

Run:

```bash
comfy node validate
comfy node pack
python -m pytest -q tests/package --archive node.zip
```

The first package run may emit the sorted candidate hashes for review. Commit
those exact hashes to `release/1.0.0-archive.sha256`, rerun, and require an
exact match.

**Step 5: Commit**

```bash
git add .comfyignore pyproject.toml release tests/package
git commit -m "test: inspect packed release archive"
```

### Task 5: Exercise a packed ComfyUI checkout

**Files:**
- Create: `tests/integration/conftest.py`
- Create: `tests/integration/test_packed_comfyui.py`

**Step 1: Write the harness assertions first**

Define pytest options `--comfy-ref`, `--archive`, and `--device`. Fail clearly
when required options, Git, or the requested CUDA device are unavailable.

Test helpers independently for safe extraction, loopback port selection,
process cleanup, HTTP timeout handling, log redaction, `/object_info`
comparison, prompt submission, terminal history polling, and expected output
files.

**Step 2: Verify helper RED**

Run:
`python -m pytest -q tests/integration -k "not packed"`

Expected: helper tests fail before implementation.

**Step 3: Implement one end-to-end packed test**

Using only the standard library and pytest:

1. clone the exact stable tag into pytest temporary storage;
2. create its virtual environment and install its requirements;
3. safely extract `node.zip` beneath `custom_nodes/lfgg-nodes`;
4. install the extracted node non-editably;
5. start `main.py` on `127.0.0.1` with temporary input/output roots;
6. compare `/object_info` to `release/1.0.0-schema.json`;
7. submit `workflows/sizing.json`, wait for completion, and verify outputs;
8. terminate the process in `finally`, exposing bounded logs only on failure.

Set the requested CPU/CUDA ComfyUI flags in one small mapping. Do not add a
second runner script or framework.

**Step 4: Verify against the available local target**

Run:
`python -m pytest -q tests/integration --comfy-ref v0.28.0 --archive node.zip --device cpu`

Expected: pass when the environment can install ComfyUI; otherwise record the
specific environmental limitation without claiming success.

**Step 5: Commit**

```bash
git add tests/integration
git commit -m "test: exercise packed ComfyUI install"
```

### Task 6: Add read-only qualification CI

**Files:**
- Create: `.github/workflows/qualify.yml`

**Step 1: Resolve immutable action pins**

For every reusable action, resolve the intended signed release tag to its full
40-character commit SHA and verify it against the official repository. Use
only `actions/checkout`, `actions/setup-python`, and artifact upload/download
unless the workflow demonstrably needs another action.

**Step 2: Add the accepted non-Cartesian jobs**

Set workflow-level `permissions: contents: read`. Add:

- lint/unit on Ubuntu Python 3.10 and 3.13 plus Windows Python 3.13;
- Registry validation and pack/package on Ubuntu Python 3.13;
- packed CPU integration on Linux and Windows for each distinct supported tag;
- protected CUDA integration only for trusted `push`, tag, or manual events on
  `[self-hosted, linux, x64, cuda]`.

As of 2026-07-26, current official releases identify `v0.28.0` as both the
minimum and latest stable, so run that combination once. Do not test `master`
as a support target.

Ensure pull requests never schedule self-hosted CUDA jobs and no test job
references Registry credentials.

**Step 3: Check workflow structure locally**

Parse the YAML through the available GitHub/comfy validation path and inspect
the diff for unpinned `uses:`, write permissions, `pull_request_target`, or
secret references.

**Step 4: Commit**

```bash
git add .github/workflows/qualify.yml
git commit -m "ci: qualify sizing release"
```

### Task 7: Add protected tag publication

**Files:**
- Create: `.github/workflows/release.yml`
- Modify: `README.md`

**Step 1: Add tag/version and credential-boundary checks**

The workflow triggers only on `v*.*.*`. Before any environment or secret is
referenced, verify the tag is exactly `vX.Y.Z`, matches `pyproject.toml`, rerun
qualification, repack, and compare the approved content manifest.

**Step 2: Add the publish job**

The publish job:

- depends on all qualification jobs;
- uses `environment: registry-release`;
- has `permissions: contents: read`;
- is the only job referencing `secrets.REGISTRY_ACCESS_TOKEN`;
- checks out the exact tag with a full-SHA-pinned action;
- installs a reviewed comfy-cli version;
- repacks and rechecks the content manifest;
- runs `comfy node publish` with the token through its documented environment
  interface; and
- verifies the public Registry version and clean install before succeeding.

Do not create the environment, token, tag, or publication during this task.
Those external mutations wait for the final release approval.

**Step 3: Document operator prerequisites**

README must say that `registry-release` requires reviewer `lfelipegg`, the
publisher-scoped token is environment-scoped, and consumed Registry versions
are incremented/deprecated rather than overwritten.

**Step 4: Commit**

```bash
git add .github/workflows/release.yml README.md
git commit -m "ci: gate Registry publication"
```

### Task 8: Final verification, review, and issue handoff

**Files:**
- Modify as findings require: files changed above

**Step 1: Run local gates**

```bash
python -m ruff check .
python -m pytest -q tests/unit
comfy node validate
comfy node pack
python -m pytest -q tests/package --archive node.zip
python -m pytest -q tests/integration --comfy-ref v0.28.0 --archive node.zip --device cpu
git diff --check
```

Record every skipped or unavailable check explicitly.

**Step 2: Review against both tickets**

Run the repository code-review workflow against the pre-implementation commit.
Fix only concrete standards/spec findings, rerun affected checks, and commit
the fixes.

**Step 3: Refresh indexed Markdown**

Run:
`python3 .codex-context/ctx.py ingest`

Expected: fresh index with no stale Markdown sources.

**Step 4: Confirm clean committed state**

Run:
`git status --short --branch`

Expected: no tracked or untracked release work remains except ignored
`node.zip`.

**Step 5: Handoff external gates**

Report commits, checks, archive manifest identity, and limitations. Request
release approval only after remote Linux/Windows/CPU/CUDA jobs pass. Then
configure `registry-release`, add its token, create exact tag `v1.0.0`,
publish, verify the Registry page and fresh install, and close issues #14 and
#15 with evidence.
