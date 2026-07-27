# Sizing Release Qualification Corrections

Purpose: Close the concrete qualification gaps found while finishing issue #15.
Read when: fixing or reviewing the 1.0.0 package, integration, and Registry release gates.
Do not read for: sizing-node behavior; use the accepted sizing release design.
Source of truth: issues #11, #14, and #15 plus the package verification contract.
Last reviewed: 2026-07-26

## Summary

- Make clean development environments install the declared build backend.
- Reject every non-regular ZIP member and cover each archive limit.
- Verify packed workflow outputs and sanitize successful logs and responses.
- Exercise the exact published version through `comfy node install`.

## Design

Keep the existing harnesses and workflows. Add `setuptools>=77` to the development
extra because package tests intentionally build without isolation. Tighten the
standard-library ZIP inspector to accept only directories and regular files, and
add focused tests for member count, cumulative size, unsafe modes, and local or
secret content in the candidate.

The packed integration harness will validate the returned output descriptors,
non-empty latent files, and expected latent tensor shapes using the temporary
ComfyUI environment. Successful responses and retained failure logs will be
checked after redaction so credentials, metadata payloads, and workspace paths
cannot escape the harness.

After publication, the release workflow will install `lfgg-nodes@<exact-version>`
with comfy-cli into a fresh ComfyUI checkout and run the same sizing workflow.
The direct Registry archive download remains because it proves the published
archive matches the approved manifest.

## Alternatives Rejected

- Patching only the CI install command leaves documented local development broken.
- Enabling build isolation makes the archive test depend on an extra network build.
- Replacing the current harnesses would add machinery without improving coverage.
