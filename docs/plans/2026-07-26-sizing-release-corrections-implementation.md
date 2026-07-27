# Sizing Release Qualification Corrections Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the 1.0.0 package, integration, and protected publication gates satisfy issues #11 and #15 on clean environments.

**Architecture:** Keep the existing standard-library archive and integration harnesses. Tighten their trust boundaries and assertions in place, then add one installed-workspace path so the tag workflow can exercise the exact Registry-installed version without duplicating the server runner.

**Tech Stack:** Python 3.10–3.13, pytest, `zipfile`, `urllib`, comfy-cli 1.12.0, ComfyUI v0.28.0, GitHub Actions.

---

### Task 1: Install the build backend in development environments

**Files:**
- Modify: `tests/unit/test_contract.py`
- Modify: `pyproject.toml`
- Modify after packing: `release/1.0.0-archive.sha256`

**Step 1: Write the failing metadata assertion**

In `test_metadata_manifest_and_workflow_match_the_release_contract`, assert:

```python
assert "setuptools>=77" in project["optional-dependencies"]["dev"]
```

Use the actual `metadata["project"]` table already loaded by the test.

**Step 2: Verify RED**

Run:
`python -m pytest -q tests/unit/test_contract.py::test_metadata_manifest_and_workflow_match_the_release_contract`

Expected: fail because the development extra omits the declared build backend.

**Step 3: Implement the minimum dependency fix**

Add `"setuptools>=77"` to `[project.optional-dependencies].dev`. Do not add it to runtime dependencies.

**Step 4: Verify GREEN and the original clean-environment reproduction**

Run the focused unit test, then create a temporary venv, install `.[dev]`, and run:

```bash
python -m pip wheel --no-build-isolation --no-deps <extracted-node.zip>
```

Expected: both commands pass without `ModuleNotFoundError: setuptools`.

**Step 5: Commit**

```bash
git add pyproject.toml tests/unit/test_contract.py
git commit -m "fix: install package build backend for qualification"
```

Refresh the archive manifest only after all packaged source changes are complete.

### Task 2: Complete archive trust-boundary checks

**Files:**
- Modify: `tests/package/test_archive.py`
- Modify: `tests/package/archive.py`

**Step 1: Write focused failing tests**

Add one test for each missing branch:

- monkeypatch `MAX_MEMBERS` to `1` and reject a two-member ZIP;
- monkeypatch `MAX_TOTAL_BYTES` to `3` and reject two two-byte members;
- construct FIFO, socket, character-device, and block-device `ZipInfo` modes and reject each as an unsafe member type;
- for the real candidate, assert concatenated member contents contain neither the repository absolute path nor any non-empty value from `REGISTRY_ACCESS_TOKEN`, `COMFY_API_KEY`, `COMFY_CLOUD_API_KEY`, or `GITHUB_TOKEN`.

**Step 2: Verify RED**

Run:
`python -m pytest -q tests/package/test_archive.py -k "member_limit or total_limit or unsafe_member_type or sensitive_content" --archive node.zip`

Expected: unsafe non-symlink modes are accepted and the new limit tests expose uncovered branches.

**Step 3: Reject special member modes**

Keep the explicit symlink error. For nonzero Unix mode bits, accept only `stat.S_ISREG(mode)` or `stat.S_ISDIR(mode)`; otherwise raise `ValueError("unsafe archive member type: <path>")`.

**Step 4: Verify GREEN**

Run:
`python -m pytest -q tests/package --archive node.zip`

Expected: all package tests pass.

**Step 5: Commit**

```bash
git add tests/package
git commit -m "test: complete archive boundary coverage"
```

### Task 3: Harden Registry download boundaries

**Files:**
- Modify: `tests/integration/test_packed_comfyui.py`
- Modify: `tests/integration/harness.py`

**Step 1: Write failing URL and response tests**

Add focused tests that:

- reject `localhost`, `.localhost`, and hostnames whose `socket.getaddrinfo` results contain loopback, private, link-local, multicast, reserved, or unspecified addresses;
- reject an HTTPS redirect to a non-public target before following it;
- reject invalid and negative `Content-Length`;
- reject a chunked body larger than the configured limit;
- time out after a persistent Registry version mismatch with `time.monotonic`/`sleep` monkeypatched;
- remove a newly created partial destination when writing raises.

**Step 2: Verify RED**

Run:
`python -m pytest -q tests/integration/test_packed_comfyui.py -k "registry or public or redirect or content_length or partial"`

Expected: the new DNS, redirect, and uncovered response-branch checks fail.

**Step 3: Implement public-host and redirect validation**

Use `socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)` and require every returned address to satisfy `ip_address(address).is_global`. Add an `HTTPRedirectHandler` subclass whose `redirect_request` calls the same validator before delegating. Use one module-level opener for both Registry requests.

Keep the existing size, timeout, exclusive-create, and cleanup behavior.

**Step 4: Verify GREEN**

Run the focused test command, then:
`python -m pytest -q tests/integration -k "not packed"`

Expected: helper tests pass.

**Step 5: Commit**

```bash
git add tests/integration/harness.py tests/integration/test_packed_comfyui.py
git commit -m "test: harden Registry archive download"
```

### Task 4: Verify packed outputs and disclosure handling

**Files:**
- Modify: `tests/integration/test_packed_comfyui.py`
- Modify: `tests/integration/harness.py`

**Step 1: Write failing result assertions**

Extend the packed result assertion to require:

```python
{
    "lfgg/sizing/aspect_ratio_00001_.latent": [1, 4, 72, 128],
    "lfgg/sizing/long_side_00001_.latent": [2, 4, 36, 64],
    "lfgg/sizing/pixel_budget_00001_.latent": [2, 4, 27, 48],
}
```

Add a helper test proving credentials, serialized workflow metadata, and workspace paths are absent after sanitizing a successful log/response.

**Step 2: Verify RED**

Run the helper selection and the packed CPU integration test. Expected: `output_shapes` and success-path disclosure validation are absent.

**Step 3: Implement the minimum shared exercise assertions**

- Compare history `SaveLatent` descriptors with files found beneath the output root.
- Invoke the temporary ComfyUI Python to read each `.latent` with `safetensors.safe_open` and return `latent_tensor` shapes as JSON.
- Require every output file to be non-empty.
- Apply one disclosure helper to serialized `/object_info`, prompt response, history, and the redacted successful log. Check active credential values, serialized workflow metadata, and workspace path variants.

**Step 4: Verify GREEN**

Run:
`python -m pytest -q tests/integration --comfy-ref v0.28.0 --archive node.zip --device cpu`

Expected: all integration tests pass and exact latent shapes are reported.

**Step 5: Commit**

```bash
git add tests/integration
git commit -m "test: verify packed sizing outputs"
```

### Task 5: Exercise the exact Registry-installed version

**Files:**
- Modify: `tests/integration/conftest.py`
- Modify: `tests/integration/test_packed_comfyui.py`
- Modify: `tests/integration/harness.py`
- Modify: `tests/unit/test_release_workflows.py`
- Modify: `.github/workflows/release.yml`

**Step 1: Write failing option and workflow assertions**

Add `--installed-comfyui` as an optional exact checkout path, mutually exclusive with `--comfy-ref`. Add a test that the release workflow:

- creates a fresh comfy-cli workspace for ComfyUI `0.28.0` on CPU;
- installs `"lfgg-nodes@${version}"` with `comfy node install --exit-on-fail`;
- runs the integration suite with `--installed-comfyui`;
- keeps the direct Registry archive download and manifest check.

**Step 2: Verify RED**

Run:
`python -m pytest -q tests/unit/test_release_workflows.py tests/integration/test_packed_comfyui.py -k "installed or release"`

Expected: the option, installed-workspace runner, and release commands are absent.

**Step 3: Reuse the existing server runner**

Extract the post-install server/exercise portion of `run_packed_comfyui` into one private function. Add `run_installed_comfyui` that:

- resolves the supplied ComfyUI checkout;
- proves it is a v0.28.0 checkout with an environment Python;
- proves the installed node directory exists beneath `custom_nodes`;
- invokes the same server, schema, workflow, output, and disclosure checks without extracting or pip-installing the candidate archive.

Keep `run_packed_comfyui` behavior unchanged for qualification CI.

**Step 4: Add protected release commands**

After direct published-archive verification, use a `$RUNNER_TEMP` workspace:

```bash
comfy --workspace="$REGISTRY_WORKSPACE" install --version 0.28.0 --cpu
comfy --workspace="$REGISTRY_WORKSPACE" node install "lfgg-nodes@${VERSION}" --exit-on-fail
python -m pytest -q tests/integration \
  --installed-comfyui "$REGISTRY_WORKSPACE/ComfyUI" \
  --device cpu
```

Pass `VERSION` from `needs.tag.outputs.version`. Keep credentials absent from these verification steps.

**Step 5: Verify GREEN**

Run the focused unit/helper tests. The live Registry-installed path remains tag-gated and must be recorded as unavailable before publication.

**Step 6: Commit**

```bash
git add .github/workflows/release.yml tests/integration tests/unit/test_release_workflows.py
git commit -m "ci: verify clean Registry installation"
```

### Task 6: Refresh the candidate and run final gates

**Files:**
- Modify: `release/1.0.0-archive.sha256`
- Modify: `docs/plans/2026-07-26-sizing-release-corrections-design.md`
- Add: `docs/plans/2026-07-26-sizing-release-corrections-implementation.md`

**Step 1: Regenerate and review the candidate**

Run `comfy node validate` and `comfy node pack`. Generate sorted content hashes through the package inspector, update only changed approved hashes, and rerun package tests.

**Step 2: Run all local gates**

```bash
python -m ruff check .
python -m pytest -q tests/unit
comfy node validate
comfy node pack
python -m pytest -q tests/package --archive node.zip
python -m pytest -q tests/integration --comfy-ref v0.28.0 --archive node.zip --device cpu
git diff --check
python3 .codex-context/ctx.py ingest
```

**Step 3: Review**

Run the repository two-axis code review against `213f5e3`. Fix only concrete findings and rerun affected checks.

**Step 4: Commit**

```bash
git add release docs/plans
git commit -m "docs: approve corrected sizing release candidate"
```

**Step 5: Handoff**

Push the branch only after user approval. Re-run the remote qualification workflow; do not create `v1.0.0` until Linux/Windows package/unit/CPU and protected CUDA jobs pass. Publication and the live Registry-install path remain environment-approved external gates.
