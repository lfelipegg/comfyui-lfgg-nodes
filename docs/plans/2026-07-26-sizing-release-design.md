# Sizing 1.0.0 Release Design

Purpose: Define the approved implementation shape for completing the sizing
family and qualifying its first release.
Read when: implementing GitHub issues #14 and #15.
Do not read for: unrelated future node families.
Source of truth: issues #5, #11, #14, and #15 plus current official ComfyUI,
Registry, and GitHub documentation.
Last reviewed: 2026-07-26

## Summary

- Complete issue #14 before issue #15 because the release depends on all three
  sizing nodes and their migration guide.
- Reuse one standard-library sizing fitter through three thin V1 adapters.
- Qualify the exact packed archive, not the editable checkout.
- Keep publication behind remote CI, protected-environment approval, and the
  environment-scoped Registry token.

## Sizing Architecture

Extend `lfgg_nodes/sizing.py` with one ComfyUI-independent fitter that accepts
source dimensions plus hard axis and pixel constraints. It selects positive
aligned dimensions by symmetric relative aspect error, then area, then the
existing deterministic side-size tie-break.

`LFGG_DimensionsByAspectRatio` continues to use the same helper. The two new
image adapters validate a real Torch `IMAGE` tensor shaped `[B,H,W,C]`, inspect
only its shape, derive the continuous long-side or pixel-budget target, and
pass integer ceilings to the helper. They never allocate, copy, cast, mutate,
or move the image.

Register exactly the three accepted V1 IDs in `LFGG/sizing`. Add no aliases,
frontend code, routes, custom wire types, latent allocation, model selector, or
runtime dependency.

## Release Artifacts

Commit one machine-readable release schema manifest covering every registered
node. Extend the model-free sizing workflow to exercise all three nodes against
native latent initializers.

Use the standard library `zipfile` module for package tests. Inspect every
archive member before extraction, reject unsafe or duplicate paths, compare
sorted archive-relative content hashes with the approved manifest, and assert
that development, private, cached, and local data are absent.

The packed integration harness receives an exact ComfyUI checkout and
`node.zip`, installs the archive non-editably, starts ComfyUI on loopback with
temporary roots, checks `/object_info` against the release manifest, and runs
the complete sizing workflow. It remains an explicit integration command, not
part of fast unit tests.

## CI and Publication

The pull-request workflow runs read-only lint, unit, Registry validation,
package inspection, and the accepted non-Cartesian packed integration matrix.
CUDA jobs run only trusted repository code. Every third-party action is pinned
to a verified full commit SHA.

The tag workflow accepts only exact `vX.Y.Z` tags matching `pyproject.toml`,
repeats mandatory gates without credentials, and passes the exact approved
archive to a separate publish job. Only that job references the protected
`registry-release` environment and its `REGISTRY_ACCESS_TOKEN`.

Creating `v1.0.0`, configuring the protected environment/token, publishing, and
verifying a fresh Registry install happen only after remote checks pass and the
release approval is explicitly granted. A consumed bad Registry version is
never overwritten or retried.

## Documentation and Verification

Update the README with the three-node table, exact tested support, Registry and
manual installation instructions, file/network disclosure, workflows, and
migration mappings. Document native `ImageFromBatch`, explicit model labels,
and the deferred prompt and LoRA families.

Write behavior tests before implementation and watch them fail. Run focused
tests during each slice, then Ruff, all unit/package tests, Registry validation,
archive inspection, and available packed integration checks. Remote Windows
and CUDA results are required before support or publication is claimed.
