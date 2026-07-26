# Package Verification and Distribution Contract

Purpose: Define the commands and release gates for the `lfgg-nodes` successor pack.
Read when: implementing development tooling, tests, CI, packaging, or a Registry release.
Do not read for: successor-node behavior; use the relevant closed Wayfinder ticket.
Source of truth: the linked Wayfinder decisions and current official ComfyUI, Registry, and GitHub documentation.
Last reviewed: 2026-07-26

## Summary

- Fast checks use Ruff and pytest; integration installs and exercises `node.zip`, never the editable checkout.
- The accepted successor nodes are Python-only, so there is no generated-asset build step.
- Release support is ComfyUI v0.28.0 through the latest tested stable tag, Python 3.10–3.13, Linux/Windows, and CPU/NVIDIA CUDA.
- Registry publication is tag-gated, manually approved, and receives its token only through the protected `registry-release` environment.

This repository is still research-only. The commands below become runnable acceptance criteria for the implementation tickets that add their referenced metadata, tests, and workflows.

## Canonical commands

Run commands from the successor-pack root with the same Python environment selected for ComfyUI.

| Purpose | Command |
|---|---|
| Confirm the development ComfyUI | `comfy which` |
| Install development tools | `python -m pip install -e ".[dev]"` |
| Lint and static security rules | `python -m ruff check .` |
| Unit and contract tests | `python -m pytest -q tests/unit` |
| Registry metadata/security validation | `comfy node validate` |
| Generated-asset build | None while the pack remains Python-only |
| Create the Registry candidate | `comfy node pack` |
| Inspect the candidate | `python -m pytest -q tests/package` |
| Exercise a packed ComfyUI install | `python -m pytest -q tests/integration --comfy-ref <stable-tag> --archive node.zip --device <cpu-or-cuda>` |

`[project.optional-dependencies].dev` owns Ruff, pytest, and comfy-cli. `[project].dependencies` is a static list of direct runtime dependencies only. Do not add a compatibility `requirements.txt`, a build wrapper, or a second command runner.

The accepted designs need no new framework or frontend dependency. Do not declare or pin ComfyUI's Torch stack. A sizing-only release has no runtime dependency; a release containing `LFGG_SaveImageDynamic` declares Pillow because that node imports it. Add lower or upper bounds only after the supported matrix proves them.

If browser assets are accepted later, revise this contract with one real build command and test its built output. Do not add a placeholder Node toolchain now.

## Fast test gate

`python -m pytest -q tests/unit` must cover:

- root import, complete V1 registration, unique `LFGG_` IDs, `LFGG ` display names, callable schemas, and duplicate rejection;
- the release's expected node-ID/schema manifest and absence of legacy aliases;
- every non-trivial behavior, validation, parser, path, collision, cleanup, and error branch accepted by the node-plan tickets;
- real Torch tensors for image shape, batch, dtype, device, immutability, and finite-value behavior—never tensor mocks;
- CPU behavior on every pull request and real CUDA tensors on the release CUDA runner;
- deterministic filesystem tests using temporary roots, including traversal, symlink escape, exclusive creation, rollback, and no absolute-path leakage; and
- `pyproject.toml`, README support claims, registered IDs, workflow fixtures, and dependency declarations remaining synchronized.

`python -m ruff check .` is blocking. Its checked-in configuration must reject `eval`, `exec`, multiple statements used to hide prohibited code, undefined names, and ordinary correctness errors. `comfy node validate` is an additional Registry check, not a substitute for the blocking lint and behavior gates.

## Candidate archive gate

`comfy node pack` must create `node.zip` from Git-tracked files plus explicit `[tool.comfy].includes`, filtered by the committed `.comfyignore`.

`tests/package` must inspect and safely extract that archive, then assert:

- root `__init__.py`, runtime modules/data, `pyproject.toml`, README, LICENSE, and any required user-facing workflow/help assets are present;
- generated frontend assets are absent while no frontend exists;
- tests, caches, coverage, source-control data, local paths, credentials, private data, large samples, and unrelated research are absent;
- the archive contains no absolute or traversal member and no duplicate member; and
- a clean ComfyUI environment can install the extracted package non-editably from its declared metadata.

The test records a sorted manifest of archive-relative paths and content hashes. That manifest is the release candidate identity; zip timestamps or compression bytes are not.

## Packed integration gate

The pytest integration harness must:

1. create a clean environment for the exact ComfyUI stable tag;
2. extract `node.zip` beneath that checkout's `custom_nodes/lfgg-nodes`;
3. install the extracted package and its declared dependencies with that ComfyUI Python;
4. start ComfyUI on loopback with a temporary input/output root and fail on import errors;
5. query `/object_info` and compare every shipped `LFGG_` ID, input order/type/default/bounds/combo, output, category, and display name with the release manifest;
6. submit the tracked API-format workflows, wait for terminal completion, and verify returned data/files;
7. assert logs and responses contain no credentials, metadata contents, or local absolute paths; and
8. stop the server and retain useful logs only on failure.

The repository must carry one small, model-free workflow per accepted family:

- **Sizing successors:** exercise `LFGG_DimensionsByAspectRatio`, `LFGG_ImageDimensionsByLongSide`, and `LFGG_ImageDimensionsByPixelBudget`, connecting each output pair to an appropriate native latent initializer.
- **Dynamic image save:** feed a small generated image batch through `LFGG_SaveImageDynamic`; verify PNG contents, metadata on/off behavior, collision-safe names, output-relative UI descriptors, and files confined beneath the temporary output root.

Each workflow uses only ComfyUI core plus this pack. A release runs every workflow whose family it ships.

## Required CI matrix

Do not run the full Cartesian product. The smallest release-blocking matrix is:

| Gate | Required jobs |
|---|---|
| Lint/unit | Linux Python 3.10 and 3.13; Windows Python 3.13 |
| Pack/package | Linux Python 3.13 |
| Packed CPU integration | Linux and Windows at v0.28.0 and the pinned latest stable ComfyUI tag |
| Packed CUDA integration | NVIDIA Linux runner at v0.28.0 and the pinned latest stable ComfyUI tag |

When the minimum and latest stable tags are identical, run that combination once. Current ComfyUI `master` may be an allowed-to-fail early-warning job but is never a supported target. macOS, ROCm, Metal, XPU, and NPU classifiers remain absent until an equivalent real integration run passes.

Pull-request CI runs lint/unit, pack/package, and hosted CPU integration with read-only permissions. CUDA is release-blocking on the protected NVIDIA runner; untrusted pull-request code must not run there. All reusable Actions are pinned to verified full commit SHAs.

## Metadata contract

`pyproject.toml` is authoritative and must contain:

- package name `lfgg-nodes`, display name `LFGG Nodes`, publisher `lfelipegg`, and one three-part SemVer version;
- MIT license metadata plus the packaged LICENSE;
- repository, README documentation, and issue-tracker URLs;
- `requires-python = ">=3.10,<3.14"` and `[tool.comfy].requires-comfyui = ">=0.28.0"`;
- no `comfyui-frontend-package` constraint while the pack has no browser code;
- Linux and Windows classifiers plus NVIDIA CUDA if the current Registry taxonomy accepts it; document CPU support in the README because the Registry specification lists no CPU classifier; and
- static runtime dependencies with platform markers where needed.

Before a release, compare registered IDs and persisted schemas with the previous version. Breaking workflow contracts require a major version; compatible features require a minor version; compatible fixes require a patch version.

## Tag and publication gate

Publication is allowed only for an exact `vX.Y.Z` tag whose version matches `pyproject.toml`. Pushes to `main` and ordinary metadata changes must never publish.

The release workflow must:

1. rerun every mandatory gate against the exact tag without Registry credentials;
2. preserve the approved archive manifest and confirm the checkout remains unchanged;
3. wait for approval in the protected `registry-release` environment;
4. expose the publisher-scoped `REGISTRY_ACCESS_TOKEN` only to the publish job;
5. install a reviewed comfy-cli version, repack in the unchanged tagged workspace, and compare its content manifest with the approved manifest;
6. run `comfy node publish` from that workspace with a concise changelog;
7. verify the Registry page; and
8. install the exact published version into a fresh ComfyUI environment and rerun the release workflows.

The workflow uses `permissions: contents: read`, never executes untrusted code through `pull_request_target`, and never passes the release secret to test jobs. `lfelipegg` is the initial required reviewer; self-approval remains enabled while the project has one maintainer.

Registry versions are immutable. If Registry version creation succeeds before a later step fails, treat that version as consumed: fix the cause, increment the version, and deprecate the bad version with an actionable replacement. Never overwrite or retry the consumed version.

## Release-readiness checklist

- [ ] All canonical commands passed on the exact tag.
- [ ] Minimum/latest stable, Linux/Windows, Python endpoints, CPU, and CUDA claims match the completed matrix.
- [ ] `/object_info` matches the release manifest and exposes no legacy or duplicate IDs.
- [ ] Every shipped family workflow passed from the packed archive.
- [ ] Real Torch and filesystem boundary tests passed on their required runners.
- [ ] Runtime dependencies are static, minimal, and installation-tested; no runtime installer exists.
- [ ] `node.zip` and its content manifest passed inspection with no secret, private, local, or development-only files.
- [ ] README compatibility, installation, network/file-write disclosure, node table, and migration notes match the release.
- [ ] Tag/version/SemVer classification and changelog are correct.
- [ ] The `registry-release` approval and environment-scoped token are configured.
- [ ] The published Registry version and a clean Registry install were verified.

## Evidence

Project decisions:

- [Choose the successor compatibility and registration baseline](https://github.com/lfelipegg/comfyui-lfgg-nodes/issues/3#issuecomment-5084854768)
- [Choose package identity, licensing, and release governance](https://github.com/lfelipegg/comfyui-lfgg-nodes/issues/4#issuecomment-5085195076)
- [Plan the image sizing and latent successor family](https://github.com/lfelipegg/comfyui-lfgg-nodes/issues/5#issuecomment-5085397879)
- [Plan the Save Image Dynamic successor](https://github.com/lfelipegg/comfyui-lfgg-nodes/issues/10#issuecomment-5085601649)

Current official sources rechecked on 2026-07-26:

- [ComfyUI v0.28.0 release](https://github.com/Comfy-Org/ComfyUI/releases/tag/v0.28.0) and [Python metadata](https://raw.githubusercontent.com/Comfy-Org/ComfyUI/v0.28.0/pyproject.toml)
- [ComfyUI Registry metadata specification](https://docs.comfy.org/registry/specifications)
- [ComfyUI Registry publishing and `.comfyignore`](https://docs.comfy.org/registry/publishing)
- [ComfyUI Registry standards](https://docs.comfy.org/registry/standards)
- [ComfyUI custom-node CI/CD](https://docs.comfy.org/registry/cicd)
- [comfy-cli node command source](https://github.com/Comfy-Org/comfy-cli/blob/main/comfy_cli/command/custom_nodes/command.py)
- [ComfyUI `/object_info` and `/prompt` server source](https://github.com/Comfy-Org/ComfyUI/blob/master/server.py)
- [GitHub Actions secure-use guidance](https://docs.github.com/en/actions/reference/security/secure-use)
- [GitHub deployment environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)
