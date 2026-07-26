# ComfyUI custom-node research

Research snapshot: **2026-07-26**.

This directory records the platform facts and local reference patterns that
should guide this repository's custom nodes. It is research, not a scaffold:
the node set and its compatibility target still need to be chosen.

## Read this first

1. [Custom-node API and execution](custom-node-api.md) — registration, V1/V3,
   schemas, types, execution, caching, lazy inputs, server routes, and frontend
   boundaries.
2. [Distribution and quality](distribution-and-quality.md) — repository
   layout, dependencies, Registry publishing, tests, compatibility, security,
   documentation, and releases.
3. [Local reference audit](reference-audit.md) — what is reusable in
   `reference/custom-nodes`, what is dated, and which examples are best for
   specific jobs.

## Source policy

When sources disagree, use this order:

1. Pinned ComfyUI/backend or frontend source that implements the behavior.
2. Current official ComfyUI documentation.
3. Official examples and generators.
4. Local reference nodes.

This order matters. The official docs, core example, and cookiecutter do not
currently describe one uniform generation of the custom-node API.

### Pinned upstream snapshot

| Upstream | Revision used | Why it matters |
| --- | --- | --- |
| [ComfyUI](https://github.com/Comfy-Org/ComfyUI/tree/806e092ed42772e4ce7abf44c97c50021cc4bd10) | `806e092e` | Runtime loader, execution engine, public `comfy_api`, examples; project version `0.28.0` |
| [ComfyUI docs](https://github.com/Comfy-Org/docs/tree/089ba2630c7c6a4caab5a686659a2f44b0681f4f) | `089ba263` | Authoring, migration, Registry, and UI guidance |
| [ComfyUI frontend](https://github.com/Comfy-Org/ComfyUI_frontend/tree/4916efd7fe2a80e0b08a32e6c08c41617c8a4dd7) | `4916efd7` | Extension and embedded node-help behavior |
| [Comfy CLI](https://github.com/Comfy-Org/comfy-cli/tree/85b62da3d660edf13bb3d79ab484aad40cace412) | `85b62da3` | Node initialization and Registry tooling |
| [Official cookiecutter](https://github.com/Comfy-Org/cookiecutter-comfy-extension/tree/cf4077f11804e009e15b7b399a1b062e317c77e6) | `cf4077f1` | Generated project and test layout; still V1 |

Live documentation can change after this snapshot. Recheck the V3 stability
flags and Registry requirements immediately before implementation or release.

## Decisions supported by the research

### 1. Choose one node API per import module

ComfyUI currently supports both:

| Goal | Sensible choice | Cost |
| --- | --- | --- |
| Broad compatibility with existing installs and references | V1: `NODE_CLASS_MAPPINGS` | Legacy schema; new schema-only features are unavailable |
| Newest schema features on a controlled, current ComfyUI baseline | V3: `ComfyExtension` + `io.Schema` | Public versions used for real nodes are still marked unstable and can move |

The runtime checks V1 registration before V3 and returns after finding it.
Exporting both from one module is therefore not a compatibility strategy: the
V3 entrypoint will be ignored.

### 2. Treat schema identifiers as persisted API

Node IDs are global and workflow JSON persists node type, inputs, outputs, and
widget ordering. Use an `LFGG` prefix, stable input/output identifiers, and
explicit migrations for breaking schema changes. Display names and categories
may be friendlier, but they are not substitutes for stable IDs.

### 3. Keep the executable center independent of ComfyUI

Put ordinary transformation logic in small functions and keep registration,
tensor-shape adaptation, UI results, and ComfyUI imports at the boundary. This
makes most behavior testable without booting ComfyUI and avoids copying the
large, import-heavy patterns found in older packs.

### 4. Distinguish batches from execution lists

An `IMAGE` is normally a float tensor shaped `[B,H,W,C]`; a `MASK` is normally
`[B,H,W]`. That leading batch dimension is data inside one execution value.
ComfyUI lists are graph-execution containers and have separate mapping rules.
Do not set list flags merely to support image batches.

### 5. Add platform surface area only when a node needs it

Start with Python nodes. Add a frontend extension only for interaction that the
schema cannot express, and add server routes only for browser/backend
communication. Avoid prototype hijacking and globally broad routes.

### 6. Package dependencies declaratively

Declare runtime dependencies in project metadata, publish through the Comfy
Registry, and never install packages from node import or execution code.
Registry rules prohibit runtime `pip` subprocesses, `eval`/`exec`, and
obfuscated code.

### 7. Ship discoverability with behavior

Use descriptions/tooltips first. When needed, ComfyUI can discover:

- node help under the extension web directory's `docs/`;
- example workflows under root `example_workflows/`;
- reusable blueprints under root `subgraphs/`;
- translations under root `locales/<language>/`.

These are cheaper and more durable than custom UI code.

## Recommended baseline for the next phase

Before scaffolding, define the first nodes and select a minimum supported
ComfyUI version. Then use the smallest layout that meets those nodes:

```text
__init__.py
nodes/
pyproject.toml
README.md
LICENSE
tests/
```

Do not add `web/`, server routes, installation scripts, or a JavaScript build
until a concrete node requires them.
