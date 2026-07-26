# ComfyUI custom-node distribution and quality guide

> Research snapshot: 2026-07-26
> Scope: developing, packaging, testing, documenting, publishing, and maintaining a reusable custom-node pack
> Evidence policy: primary sources only—official Comfy-Org documentation and repositories, current ComfyUI source, PyPA specifications, and GitHub's own Actions security guidance

## Executive recommendation

For a new public node pack:

1. Develop against a normal source installation of ComfyUI and scaffold with `comfy node scaffold`, but treat the generated project as a starting point rather than a complete production standard.
2. Use a small, conventional package layout; add browser code only when Python node behavior cannot provide the feature.
3. Put Registry metadata and a static dependency list in `pyproject.toml`. Use sensible dependency ranges because all custom nodes share the ComfyUI Python environment.
4. Choose V1 or V3 node definitions deliberately. V3 is ComfyUI's strategic direction, but V1 is still supported and is what the current official cookiecutter emits. Do not claim that V1 has stopped working or that `comfy_api.latest` is stable.
5. Make pull-request CI enforce linting, behavior tests, registration/schema tests, archive validation, and at least one real ComfyUI import/workflow test. Add frontend build/tests only if the pack has frontend code.
6. Publish immutable semantic versions through the Comfy Registry from an explicitly approved release or tag. Store `REGISTRY_ACCESS_TOKEN` only as a repository/environment secret.
7. Treat a custom node as trusted native code. Registry verification is useful evidence, not a sandbox.

The current ComfyUI project declares version `0.28.0` and Python `>=3.10`; the Registry documentation's `requires-comfyui = ">=1.0.0"` examples are illustrative, not a real minimum to copy. Derive compatibility bounds from tests against actual ComfyUI releases. See the pinned [ComfyUI `pyproject.toml`][core-pyproject] and [Registry specification][registry-spec].

## How to read status labels

- **Documented current** — stated in current official documentation.
- **Source current** — present in current official source, but not necessarily documented as public/stable.
- **Transitional** — two official paths coexist or the stated direction has not reached all official templates.
- **Legacy-compatible** — still supported or documented for compatibility, but not the preferred new-publication path in this guide.
- **Recommendation** — a maintainer practice inferred from the official runtime, packaging, or security model; not itself a ComfyUI guarantee.

The exact upstream revisions audited are listed in [Source ledger](#source-ledger). Pinning the evidence matters because the custom-node APIs and tooling are moving quickly.

## 1. Development environment and CLI workflow

The official walkthrough recommends a manual/source ComfyUI installation for custom-node development and uses `comfy-cli` to scaffold under `ComfyUI/custom_nodes` ([walkthrough][docs-walkthrough]). A practical setup is:

```bash
# Install the CLI as an isolated tool.
pipx install comfy-cli
# Alternative:
uv tool install comfy-cli

# Create or register a development ComfyUI installation.
comfy install
comfy which

# Scaffold inside the installation selected by comfy-cli.
cd /path/to/ComfyUI/custom_nodes
comfy node scaffold
```

The exact environment-selection rules and available commands are maintained in the [comfy-cli README][cli-readme]. Confirm the active target with `comfy which`; do not assume the CLI is operating on the same ComfyUI installation that a desktop launcher uses.

For an existing pack, install it into the selected ComfyUI Python environment in editable mode:

```bash
cd /path/to/ComfyUI/custom_nodes/your-node-pack
python -m pip install -e ".[dev]"
```

Then launch that same installation and inspect startup logs:

```bash
comfy launch
```

Do not confuse the two similarly named setup operations:

- `comfy node scaffold` invokes the official cookiecutter and creates a full new project skeleton.
- `comfy node init` is for an existing Git repository: it creates Registry metadata in a new `pyproject.toml`, derives repository URLs, and copies valid dependency lines from `requirements.txt` when present. It refuses to overwrite an existing `pyproject.toml`; it does not create the node implementation, tests, workflows, or documentation.

These behaviors are explicit in current [CLI command source][cli-node-command] and [CLI config source][cli-config-parser]. In any repository that already has `pyproject.toml`, inspect/edit it directly rather than deleting it just to run `init`.

**Recommendation:** keep one disposable, clean ComfyUI installation for installation/release tests. An editable developer checkout can hide missing archive files, undeclared dependencies, case-sensitivity bugs, and build artifacts that were never packaged.

### What the scaffold gives—and does not give

The official cookiecutter currently provides:

- setuptools-based `pyproject.toml`;
- Python `>=3.10`;
- optional development dependencies for pytest, Ruff, mypy, coverage, and pre-commit;
- a basic Ruff/pytest pull-request workflow;
- Registry validation and publication workflow examples; and
- V1 `NODE_CLASS_MAPPINGS` registration in the Python template.

See the pinned [template metadata][template-pyproject], [build workflow][template-ci], [registration file][template-init], and [example test][template-test].

The generated test mainly checks that the example object and metadata exist. That is scaffolding coverage, not proof that tensor behavior, caching, files, routes, device handling, workflow compatibility, or packaging works. Expand it before release.

## 2. Recommended repository layout

This is a compact layout, not a requirement that every directory exist:

```text
your-node-pack/
├── __init__.py
├── pyproject.toml
├── README.md
├── LICENSE
├── src/
│   └── your_package/
│       ├── __init__.py
│       └── nodes.py
├── tests/
│   ├── test_registration.py
│   ├── test_nodes.py
│   └── test_workflows.py
├── web/                         # only if browser assets or embedded help exist
│   ├── js/
│   │   └── extension.js
│   └── docs/
│       └── StableNodeId/
│           └── en.md
├── example_workflows/           # preferred folder name
│   ├── basic.json
│   └── basic.jpg
├── subgraphs/                   # optional reusable subgraph blueprints
│   └── useful-pattern.json
├── locales/                     # optional localization
│   └── es/
│       ├── main.json
│       ├── nodeDefs.json
│       ├── commands.json
│       └── settings.json
├── .comfyignore
└── .github/
    └── workflows/
        ├── ci.yml
        └── publish.yml
```

`__init__.py` is the ComfyUI entrypoint. It either exports the V1 mappings or a V3 `comfy_entrypoint`; do not make it load models, contact networks, install packages, or mutate the host at import time.

`src/your_package/` is the official cookiecutter convention, but ComfyUI only requires a loadable root entrypoint; a small pack can use flat Python modules. Prefer the organization that makes imports and tests obvious rather than adding packaging layers without a need.

### Workflows, subgraphs, documentation, and localization

- `example_workflows/` is the preferred workflow-template folder. Current core also recognizes `example`, `examples`, `workflow`, and `workflows`, and logs a suggestion to rename them. It does **not** recognize a root `templates/` alias. This is verified by the current [workflow scanner source][core-workflow-scanner] and agrees with the [workflow-template documentation][docs-workflows].
- Template JSON and its same-stem preview image belong directly one level below `example_workflows/`, for example `basic.json` and `basic.jpg` ([workflow-template documentation][docs-workflows]).
- Root `subgraphs/*.json` is scanned separately as reusable subgraph blueprints ([subgraph documentation][docs-subgraphs], [subgraph manager source][core-subgraph-scanner]).
- Embedded custom-node help is served from `WEB_DIRECTORY/docs/<NodeId>.md` or localized paths such as `WEB_DIRECTORY/docs/<NodeId>/en.md` ([help-page documentation][docs-help]).
- Localization uses `locales/<language>/main.json`, `nodeDefs.json`, `commands.json`, and `settings.json` as applicable ([i18n documentation][docs-i18n]).

The frontend's generic “templates” feature is not evidence that a custom node should ship a root `templates/` folder. Workflow-template discovery and frontend templates are separate mechanisms.

## 3. V1 versus V3 node definitions

This area is **transitional** as of the research date.

| Evidence | V1 | V3 |
|---|---|---|
| Current core loader | Recognizes `NODE_CLASS_MAPPINGS` and optional `NODE_DISPLAY_NAME_MAPPINGS` | Recognizes synchronous or asynchronous `comfy_entrypoint` returning a `ComfyExtension`; `get_node_list` is asynchronous |
| Current official cookiecutter | Generates V1 | Does not generate V3 |
| Current core example | Not the example's chosen API | Uses `from comfy_api.latest import ComfyExtension, io` |
| Direction in migration docs | Called the legacy schema | New versioned API; future features are intended for V3 |
| Stability caveat | Broad installed-base compatibility | `comfy_api.latest` is moving; test and state a real ComfyUI minimum |

The authoritative loader branches are visible in current [ComfyUI `nodes.py`][core-loader]. The current [core example][core-v3-example] is V3, while the official [cookiecutter entrypoint][template-init] and [nodes file][template-nodes] remain V1. The [V3 migration guide][docs-v3] describes V3 as the forward direction.

Practical choice:

- Choose **V1** when broad compatibility with older ComfyUI installations is the main requirement and the pack does not need a V3-only capability.
- Choose **V3** for a new pack that benefits from the versioned schema/API and can state and test a recent ComfyUI minimum.
- Do not expose both definitions from one entrypoint and expect both to register: the current loader uses the V1 branch first and V3 only in `elif`.
- Do not import internal core modules unnecessarily. In V3, prefer the versioned `comfy_api` surface; in V1, keep the internal dependencies as narrow as the required data/model helpers allow.
- Preserve stable node IDs in either API. They are workflow-facing identifiers, not display labels.

Calling V1 “unsupported” would be incorrect. Calling `comfy_api.latest` a frozen contract would also be incorrect. Revisit this decision whenever the official scaffold changes.

## 4. `pyproject.toml` and dependency policy

### A safe baseline

The following example favors what the current Registry CLI actually reads: a static PEP 621 dependency list. Replace every placeholder and omit compatibility bounds until they are backed by tests.

```toml
[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"

[project]
name = "publisher-node-pack"
version = "0.1.0"
description = "One sentence describing the user-visible capability."
readme = "README.md"
license = "MIT"
requires-python = ">=3.10"
dependencies = [
  # "numpy>=1.26",
  # "some-platform-package>=2; sys_platform == 'linux'",
]
classifiers = [
  "Operating System :: OS Independent",
]

[project.optional-dependencies]
dev = [
  "pytest>=8",
  "ruff",
]

[project.urls]
Repository = "https://github.com/publisher/publisher-node-pack"
Documentation = "https://github.com/publisher/publisher-node-pack#readme"
Issues = "https://github.com/publisher/publisher-node-pack/issues"

[tool.comfy]
PublisherId = "publisher-id"
DisplayName = "Publisher Node Pack"
# requires-comfyui = ">=0.x.y"  # Add only after testing this real bound.
# Icon = "https://raw.githubusercontent.com/publisher/repo/main/icon.png"
# includes = ["dist"]           # For required ignored/untracked build output.
```

The Registry requires a valid globally unique, case-insensitive project name and a three-component semantic version. `PublisherId` is required; the repository URL is required; descriptions, Python bounds, documentation/issue URLs, and compatibility classifiers are recommended. Exact name rules and supported metadata are in the [Registry specification][registry-spec].

The current ComfyUI lower Python bound is `>=3.10` ([core metadata][core-pyproject]). A node may choose a higher minimum if a dependency requires it, but CI and the README must agree with that choice.

### License metadata is in transition

Current PyPA metadata uses an SPDX license expression such as `license = "MIT"` ([PyPA `pyproject.toml` specification][pypa-pyproject], [PEP 639][pep639]). Setuptools added PEP 639 support in version 77, which is why the baseline build requirement above is `setuptools>=77`; using an older setuptools with the string form is not a compatible combination ([setuptools `pyproject.toml` documentation][setuptools-pyproject]). The current `comfy node init` implementation also writes a string license. However, current Registry prose and the official cookiecutter still show the older `license = {file = ...}` or `{text = ...}` form.

**Recommendation:** use the SPDX string accepted by current PyPA tooling and emitted by current comfy-cli, while always shipping the actual license text in `LICENSE`. If Registry validation rejects that form in a future/older deployment, follow the validator rather than silently publishing ambiguous license metadata.

The pinned comfy-cli metadata extractor recognizes `Repository`,
`Documentation`, and `Issues` URL keys. Use `Issues`, not a cosmetically
equivalent key such as `"Bug Tracker"`, or the Registry issue URL will be
omitted ([CLI config parser][cli-config-parser]).

### Static dependencies versus `requirements.txt`

Official sources currently conflict:

- The Registry specification's complete example marks `dependencies` dynamic and points setuptools at `requirements.txt`.
- Registry publishing prose says `comfy node init` fills dependencies from `requirements.txt`.
- The audited `comfy node init` does copy valid PEP 508 lines from an existing `requirements.txt` into a static `[project].dependencies` list. Later validation/publication reads that static list; the CLI does not dynamically resolve `[tool.setuptools.dynamic] dependencies` from `requirements.txt` ([CLI config parser][cli-config-parser]).
- The current Manager documentation and implementation still support installing `requirements.txt`.

Therefore:

1. Use static `[project].dependencies` as the Registry source of truth.
2. If legacy/direct Manager installation is an explicit support target, keep a matching `requirements.txt`. Add a CI parity check or generate it from one canonical input so the two lists cannot drift.
3. If the pack has no external runtime dependency, use an empty static list and do not add a ceremonial requirements file.
4. Do not rely on Registry docs' dynamic-dependency example until comfy-cli demonstrably resolves it.

This duplication is not elegant, but pretending the official paths are already unified is riskier.

### Dependency constraints and shared-environment conflicts

All custom nodes run in the same ComfyUI Python environment. One pack's over-pin can make another pack impossible to install. The older Manager guide itself warns authors not to make requirements more restrictive than necessary ([Manager publishing guide][docs-manager]).

Use these rules:

- Declare every direct runtime dependency and no test/build-only dependency.
- Prefer a tested lower bound and omit an upper bound unless a known incompatible version exists.
- Use PyPA environment markers for platform- or Python-specific packages rather than runtime installation logic ([dependency-specifier specification][pypa-dependencies]).
- Do not pin ComfyUI's own foundational stack—such as a particular Torch build—unless the node truly cannot operate with ComfyUI's supported variants.
- Do not vendor large wheels or private package installers into the node archive.
- Test installation into a clean environment that already contains ComfyUI, then test alongside likely co-installed packs.
- Document optional dependencies per feature and fail with a focused message only when that feature is invoked.

The comfy-cli README documents a Manager `v4.1+` path using `--uv-compile`/`comfy node uv-sync` to resolve all custom-node dependencies together and detect cross-node conflicts ([CLI README][cli-readme]). Treat this as **version-gated**: confirm the installed Manager supports it before making it part of user instructions. It does not remove the need for compatible dependency ranges.

### Frontend compatibility metadata

If browser code depends on a particular frontend API, add a `comfyui-frontend-package` version specifier to `[project].dependencies`. The Registry parser treats it as frontend compatibility metadata rather than an ordinary package to install ([Registry specification][registry-spec], [CLI config parser][cli-config-parser]).

Do not add this pseudo-dependency to a Python-only pack. When it is present, test at the lower bound and latest supported frontend, and make breaking frontend changes part of the node pack's semantic-version decision.

## 5. Browser assets, TypeScript, and routes

Most nodes do not need frontend code. A Python schema already provides inputs, outputs, categories, defaults, constraints, and execution. Every browser extension increases compatibility and security surface.

When JavaScript is needed, current documented registration is:

```python
# __init__.py
WEB_DIRECTORY = "./web"
```

ComfyUI serves that directory and loads JavaScript extensions from it. Extensions register with the frontend application API ([JavaScript overview][docs-js]).

Current core source also parses:

```toml
[tool.comfy]
web = "web"
```

and auto-registers that directory ([core loader][core-loader]). But `web` is absent from the current Registry metadata specification. Its status is **source current, undocumented**. For widest compatibility use documented `WEB_DIRECTORY`; if adopting `[tool.comfy].web`, do not assume older ComfyUI versions understand it, and test for duplicate/changed asset registration before combining mechanisms.

Only JavaScript is automatically loaded as an extension. Images, styles, help Markdown, and other assets are served resources or consumed by your JavaScript; do not assume every file in the directory executes.

For a small extension, checked-in plain JavaScript is the least operational burden. For TypeScript/React, use the official [ComfyUI React Extension Template][react-template] as the starting point, run its tests/build in CI, and package the built output. If build output is intentionally ignored by Git, add it to `[tool.comfy].includes`, because Registry packaging otherwise starts from Git-tracked files.

For custom HTTP routes:

- assume there is no general `PromptServer` authentication gate: `Comfy-User`
  selects a profile rather than proving identity, and Comfy account keys are
  for paid Partner Nodes, not local custom routes; put sensitive routes behind
  node-owned authorization or a trusted reverse proxy
  ([server middleware](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/server.py#L115-L190),
  [user selection](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/app/user_manager.py#L41-L55),
  [account-key scope](https://docs.comfy.org/development/comfyui-server/api-key-integration));
- namespace paths with the publisher/pack name;
- validate all request data;
- constrain file access to intended directories;
- use timeouts and bounded response sizes for remote calls;
- never return or log credentials;
- do asynchronous I/O rather than blocking ComfyUI's server loop; and
- remove/rework routes when the core API exposes the same capability.

These are maintainer security requirements derived from the fact that a custom node executes in the ComfyUI server process, not an official route sandbox.

## 6. Building the publishable archive

The current CLI exposes:

```bash
comfy node validate
comfy node pack
comfy node publish
```

`comfy node pack` creates `node.zip`. The packaging code uses `git ls-files` as its baseline, applies `.comfyignore`, and then force-includes paths named in `[tool.comfy].includes`; without Git it warns and falls back to a broader file set ([CLI command source][cli-node-command], [CLI packaging source][cli-file-utils]).

Use `.comfyignore` for tracked development-only content:

```gitignore
tests/
docs/design/
*.psd
.vscode/
.coverage
```

Do **not** exclude files required at runtime, the license, README, embedded help, example workflows, or built frontend assets. The [publishing documentation][registry-publishing] states that `.comfyignore` layers over Git tracking and that `includes` wins over ignore rules.

After every release build, inspect `node.zip` rather than trusting the checkout:

- root entrypoint is present;
- Python modules and runtime data are present;
- compiled frontend output is present;
- `pyproject.toml`, README, and license are present;
- no token, `.env`, credential, private model, cache, test artifact, source map containing secrets, or unnecessary large asset is present; and
- extracted archive imports and runs in a clean ComfyUI installation.

Editable-install tests do not prove any of these properties.

## 7. Registry publication and version lifecycle

The Comfy Registry powers current Manager discovery and provides globally unique node names, semantic versions, workflow version recording, metrics, and deprecation. Published versions are immutable ([Registry overview][registry-overview]).

### One-time setup

1. Create a publisher at the Registry. The publisher ID is globally unique and cannot later be renamed.
2. Create a publisher API key.
3. Fill `[project]`, `[project.urls]`, and `[tool.comfy]`.
4. Validate locally.
5. Store the key as `REGISTRY_ACCESS_TOKEN` in a protected repository or environment secret—never in the repository, local config committed to Git, test fixtures, or logs.

The canonical setup and manual/Actions flows are in [Registry publishing][registry-publishing].

### Metadata details that matter

- Registry project names are global and immutable after creation; choose the user-facing identity before the first publish.
- Display name can be friendlier than the immutable package ID.
- Versions are `X.Y.Z` semantic versions.
- Published bytes cannot be replaced. A bad release gets a new patch version; deprecate the bad version in the Registry UI with an actionable reason.
- The audited publish command creates the Registry version before packing and
  uploading its archive. A later pack or upload failure can therefore consume
  that immutable version number; fix the cause, increment the version, and
  publish again rather than retrying with the same version
  ([CLI command source][cli-node-command],
  [Registry backend][registry-backend-version]).
- `requires-comfyui` should describe a real tested interval. Do not copy `>=1.0.0` from the specification's example: the audited ComfyUI version is `0.28.0`.
- OS/accelerator classifiers must describe tested support, not aspirations.
- Frontend version metadata belongs only on packs with relevant browser compatibility constraints.

There is an icon-size conflict in official prose. The Registry specification requires a square image no larger than `400×400`, while the `comfy node init` example comment says `800×400`. Follow the stricter `400×400` square specification until the official sources converge.

### Publication trigger

Official examples disagree:

- the Registry publishing page triggers when `pyproject.toml` changes on `main`;
- the current cookiecutter's publish workflow triggers on a Git tag.

Both can publish, but a metadata-change trigger makes accidental immutable releases easier. **Recommendation:** publish from an explicit release tag or manually approved workflow after the exact archive passed CI.

A minimal shape is:

```yaml
name: Publish

on:
  workflow_dispatch:
  push:
    tags:
      - "v*.*.*"

permissions:
  contents: read

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: registry-release
    steps:
      - uses: actions/checkout@<full-commit-sha>
      - uses: Comfy-Org/publish-node-action@<full-commit-sha>
        with:
          skip_checkout: "true"
          personal_access_token: ${{ secrets.REGISTRY_ACCESS_TOKEN }}
```

Official examples use floating tags such as `@main`. GitHub's own security guidance says a full commit SHA is the only immutable way to reference an action ([GitHub secure-use guidance][github-actions-security]). Pin and periodically update verified commits. The audited official action revision is listed in [Source ledger](#source-ledger).

Pinning that outer composite action does not freeze its transitive supply
chain. The audited revision still invokes floating `actions/setup-python@v5`
and installs an unpinned comfy-cli, so inspect the pinned action source on
updates and use a workflow that pins every action and the comfy-cli version
when end-to-end reproducibility is required
([publish action][publish-action-source]).

The official publication action currently installs the then-current comfy-cli and `comfy node publish` creates a fresh `node.zip` immediately before upload ([publish action][publish-action-source], [CLI command source][cli-node-command]). It also creates the Registry version before packing/uploading, so a later failure can leave that version consumed. Therefore, the default path does not upload a previously preserved archive byte-for-byte and should not be blindly retried with the same version. Run validation, frontend build, `comfy node pack`, manifest inspection, and publication in one unchanged release workspace; for stricter reproducibility, control the comfy-cli version directly and compare the publish-time file manifest with the approved manifest.

The current CLI also supports release changelog text/file inputs in its command implementation ([CLI command source][cli-node-command]). Use a concise changelog that names breaking node IDs/schema changes, dependency changes, and required migration steps.

### Registry versus the older Manager-list channel

This is **transitional**, not a claim that the older channel is impossible:

- Registry docs say the Registry powers ComfyUI-Manager and make Registry publication the standardized path.
- Current Manager documentation and README still describe submitting a `custom-node-list.json` pull request, installing `requirements.txt`, and optionally running lifecycle scripts such as `install.py` ([Manager guide][docs-manager], [Manager README][manager-readme], [Manager source][manager-core]).

Use the Registry/`pyproject.toml` flow as the primary new-publication path. If a Manager-list entry is needed for compatibility/discovery, treat it as a parallel channel and keep its metadata synchronized.

An `install.py` file is not automatically forbidden merely because Manager can execute it. However, Registry standards prohibit custom-node code from spawning `pip install` at runtime, and they prohibit `eval`, `exec`, and obfuscation ([Registry standards][registry-standards]). Avoid install scripts unless an unavoidable, documented, non-package setup step exists; make every side effect idempotent and reviewable.

## 8. Test strategy

### Layer 1: fast package tests on every pull request

Required:

1. **Import and registration**
   - import root `__init__.py`;
   - assert every intended node ID is registered;
   - assert node IDs are unique within the pack;
   - validate required schema fields and that the callable exists.
2. **Behavior**
   - representative normal inputs;
   - boundary values and invalid values;
   - batch sizes greater than one;
   - empty/zero-sized cases where meaningful;
   - output shape, dtype, device, range, and semantic result.
3. **State and cache behavior**
   - deterministic nodes stay deterministic;
   - external-file nodes fingerprint the relevant file state;
   - state does not leak across workflow runs;
   - lazy inputs are requested only when needed.
4. **Files and routes**
   - traversal and malformed input rejection;
   - timeout/error behavior;
   - temporary-file cleanup;
   - no credential data in responses/logs.
5. **Metadata/package**
   - parse `pyproject.toml`;
   - dependency lists are synchronized if a compatibility `requirements.txt` exists;
   - README node table and registered IDs do not drift.

Run:

```bash
python -m pip install -e ".[dev]"
ruff check .
pytest -q
```

The official cookiecutter CI uses install + Ruff + pytest on Ubuntu/Python 3.12 ([template CI][template-ci]). Expand the matrix to the minimum and current Python versions that the pack actually promises, and add Windows/macOS jobs only when platform behavior or binary dependencies justify them.

### Layer 2: real ComfyUI integration

At least before each release, and preferably in pull-request CI:

1. install a clean supported ComfyUI version;
2. install the packed `node.zip` contents, not the editable checkout;
3. start ComfyUI and fail on custom-node import errors;
4. query node definitions and assert registered IDs/schema;
5. execute a small representative workflow;
6. verify produced data/files and server shutdown; and
7. repeat at the stated lower compatibility bound and latest stable release.

The official [Comfy-Action][comfy-action] is intended to execute workflows across Linux, macOS, and Windows, and Registry CI documentation presents it as an integration option ([Registry CI/CD][registry-cicd]). Its own README is oriented around use in the ComfyUI repository, so validate it in the node-pack repository before making it a mandatory gate. A direct scripted ComfyUI launch is acceptable when it is clearer and more reliable.

For GPU-only behavior, keep CPU/import/schema tests in normal CI and run a representative accelerator workflow on scheduled or release infrastructure. Never mark an accelerator classifier from import success alone.

### Schema compatibility checks

The official `Comfy-Org/node-diff` action compares current nodes against a prior version, but its README states that it currently checks `RETURN_TYPES` while `INPUT_TYPES` is not implemented ([node-diff README][node-diff]). Use it as an advisory signal, not a complete compatibility gate.

Maintain a versioned schema snapshot or explicit tests for:

- node ID;
- input names, types, required/optional status, defaults, ranges, and widget order where workflows serialize it;
- output order, types, names, and list/batch semantics;
- category only if external tooling depends on it; and
- replacement/migration mapping for deliberate renames.

### Validation is not a security gate by itself

The current `comfy node validate`/publish implementation invokes Ruff checks including `S102`, `S307`, and `E702` with `--exit-zero`; findings are warnings rather than a hard failure ([CLI command source][cli-node-command]). CI must run Ruff normally and fail on prohibited `exec`/`eval`:

```toml
[tool.ruff.lint]
select = [
  "E",
  "F",
  "S102",
  "S307",
]
```

`comfy node validate` remains useful for Registry configuration checks, but it does not inspect the final archive and is only one gate among several.

## 9. Compatibility and conflict policy

### Supported version matrix

Keep a small table in the README:

| Dimension | Tested support |
|---|---|
| ComfyUI | exact minimum stable tag through latest tested stable tag |
| Python | exact versions tested |
| Frontend | only if browser assets require a bound |
| OS | Linux / Windows / macOS as actually tested |
| Accelerator | CPU / CUDA / ROCm / Metal as actually exercised |

Current ComfyUI warns that commits outside stable release tags may be unstable and can break custom nodes ([ComfyUI README][core-readme]). Test:

- latest stable release as the user-facing baseline;
- the declared minimum stable version; and
- optionally current `master` as an early-warning job allowed to fail initially.

Do not set compatibility metadata from a successful import only. Run at least one workflow that touches every dependency/API used by the feature.

### Workflow compatibility is the public API

A patch/minor release should preserve:

- node IDs;
- serialized input names and expected value formats;
- output position and type;
- list/batch meaning;
- important defaults; and
- behavior users reasonably depend on.

Changing a display name is usually safer than changing the node ID. Renaming an internal Python class is harmless if the registered ID remains stable. If a schema must break, use a major version, document migration, and use V3 replacement facilities where applicable ([V3 migration guide][docs-v3]).

Semantic-version policy:

- **Patch:** bug, security, documentation, or performance fix without workflow-visible incompatibility.
- **Minor:** new backward-compatible node, optional input, or capability.
- **Major:** removed/renamed node ID, incompatible required input/output, meaningfully changed serialized value, or dependency/ComfyUI floor that strands a material supported user segment.

### Collision and interference prevention

Registry package names are globally unique, but runtime node IDs can still collide. Prefix generic IDs with a stable pack/publisher token, for example `LFGG_ImageResize` rather than `ImageResize`.

Also:

- namespace HTTP routes and frontend extension names;
- namespace settings, cache directories, temp files, and environment variables;
- never monkey-patch another node pack;
- never mutate another pack's files or dependencies;
- do not globally replace model paths or frontend menus;
- feature-detect optional peer nodes and show a clear warning at use time; and
- include a workflow demonstrating any intentional custom-node dependency.

These points implement the Registry standard that nodes must not interfere with other custom nodes and must explain peer dependencies ([Registry standards][registry-standards]).

## 10. Security and trust model

ComfyUI loads a custom node by importing and executing its Python module in the server process ([core loader][core-loader]). An official maintainer has also stated plainly that custom nodes can execute arbitrary Python code ([official discussion][security-discussion]). Therefore:

- installation grants the node the user's filesystem, network, process, model, and credential access available to ComfyUI;
- a workflow can trigger dangerous behavior exposed by an installed node;
- uninstalling the folder cannot undo arbitrary side effects; and
- Registry scanning/verification is a risk signal, not process isolation.

### Author requirements

1. No `eval` or `exec`.
2. No obfuscated code.
3. No runtime `pip install` through `subprocess`.
4. No silent shell commands, installers, telemetry, network download, or system mutation.
5. Validate workflow-provided paths, URLs, filenames, expressions, and archive contents as untrusted input.
6. Keep reads/writes inside explicit user-selected or ComfyUI-managed directories; reject traversal and symlink escape where relevant.
7. Apply network timeouts, content-size limits, protocol allowlists, and clear host information.
8. Never hardcode, commit, return, or log API tokens. Prefer environment/config references and redact error output.
9. Verify downloads when an authoritative checksum exists; do not execute downloaded content.
10. Declare dependencies in metadata; do not fetch executable Python as a convenience fallback.
11. Keep import-time behavior limited to definitions/registration.
12. Document every network call, external service, credential, file write, and optional binary.

Items 1–3 are explicit Registry rules ([Registry standards][registry-standards]); the remaining items are the minimum maintainer policy implied by unrestricted in-process execution.

### CI and release hardening

- Make prohibited-code lint rules fail.
- Review dependency changes and the final archive.
- Give workflow tokens read-only permissions unless a job needs more.
- Keep publish credentials out of pull-request jobs.
- Protect the publication environment with reviewer approval.
- Pin reusable Actions to full commit SHAs.
- Never use a privileged `pull_request_target` flow to execute an untrusted contributor checkout.
- Rotate a Registry key immediately if it appears in output or history.

These workflow precautions align with GitHub's [secure-use guidance][github-actions-security].

### User-facing trust information

README installation instructions should tell users:

- the supported official Registry/Manager identifier;
- whether the pack makes network requests or runs local executables;
- which models/files it downloads or writes;
- where credentials are read from;
- which optional peer nodes are expected; and
- how to disable/remove the pack and clean its own cache.

Do not market a Registry verification badge as a guarantee of safety. Registry docs say nodes are scanned and may receive a verification flag; they do not say execution is sandboxed ([Registry overview][registry-overview]).

## 11. Performance and resource hygiene

### Compute only what is needed

ComfyUI caches node outputs. In V3 use `fingerprint_inputs`; in V1 use `IS_CHANGED` only for external state that ordinary input comparison cannot see ([V3 migration guide][docs-v3]). A file loader should fingerprint relevant path/metadata/content. A pure node should not return a random/always-changing value, because that defeats caching.

Use lazy inputs when an upstream branch is conditional, so unused work is not evaluated ([lazy-evaluation documentation][docs-lazy]). If a complex operation can be represented as node expansion, links and subnodes allow ComfyUI to cache reusable parts rather than hiding all work inside one opaque function ([expansion documentation][docs-expansion]).

### Tensor, batch, and device discipline

- Preserve ComfyUI batch semantics; test batch size greater than one.
- Avoid unconditional `.cuda()`. Operate on the input/model's device and supported dtype.
- Avoid unnecessary CPU↔GPU copies, clones, and dtype expansion.
- Process data lists sequentially when variable-sized or large items would otherwise produce excessive VRAM use; official list guidance explicitly identifies this use case ([data-list documentation][docs-lists]).
- Do not retain model or tensor references in module globals after the operation no longer needs them.
- Do not globally empty another node's CUDA cache or change process-wide Torch settings as routine cleanup.

The last two are **recommendations** to avoid cross-pack interference in the shared process.

### Responsiveness and cleanup

- Use V3 async execution or server async APIs for network/file I/O where available.
- Report progress for long operations.
- In long Python loops, periodically honor ComfyUI interruption using the current model-management interruption helper ([model-management source][core-model-management]).
- Bound concurrency, retries, queue growth, downloaded bytes, and temporary storage.
- Close files, responses, sessions, subprocess handles, and memory maps deterministically.
- Use a pack-specific cache directory; offer a documented cleanup path.
- Load heavy models at execution time or through ComfyUI's model-management paths, not at module import.

Measure a representative workflow before claiming a performance improvement. Record wall time, peak RAM/VRAM, batch size, input dimensions, device, dtype, and cache-hot/cache-cold state.

## 12. Documentation standard

Registry standards require nodes to be functional, well documented, and actively maintained ([Registry standards][registry-standards]).

At minimum, `README.md` should contain:

1. one-paragraph purpose and non-goals;
2. screenshots or a small example workflow;
3. Registry/Manager and manual installation instructions;
4. exact node catalog with stable ID, display name, purpose, inputs, outputs, defaults, and notable constraints;
5. dependency/model requirements and download sizes;
6. tested compatibility matrix;
7. browser extension, route, network, credential, and filesystem behavior;
8. example workflows and required peer nodes;
9. troubleshooting for import, dependency, device, and missing-model failures;
10. update/deprecation/migration notes;
11. issue-report template information: ComfyUI version, pack version, frontend version, platform, accelerator, startup log, minimal workflow; and
12. license and attribution.

For every public node, add embedded help under `WEB_DIRECTORY/docs/<NodeId>/en.md` when the schema tooltip cannot adequately explain the behavior ([help-page documentation][docs-help]). The directory key is the stable node ID, so test that docs and registrations match.

Example workflows should:

- use only declared dependencies;
- avoid private absolute paths and credentials;
- use redistributable or clearly documented model requirements;
- demonstrate the simplest successful path first;
- include a same-stem preview;
- be reopened and executed from the packaged release; and
- be updated when node schemas change.

Keep a changelog. Each release should name added nodes, fixes, dependency changes, compatibility changes, deprecated IDs, migration instructions, and security-sensitive changes.

## 13. CI blueprint

A proportionate pipeline:

### Pull requests

1. Metadata parse and dependency parity.
2. Ruff hard failure, including Registry-prohibited constructs.
3. Unit/behavior/schema tests.
4. Frontend install, lint, test, and build if applicable.
5. `comfy node validate`.
6. `comfy node pack`; inspect allowlist/denylist and archive size.
7. Clean ComfyUI import/startup smoke.
8. One representative workflow.
9. Advisory `node-diff` comparison.

### Scheduled

1. Latest stable ComfyUI/front-end compatibility.
2. Optional ComfyUI `master` early warning.
3. dependency vulnerability/update review;
4. target OS/accelerator jobs that are too expensive for each PR.

### Release

1. Re-run all mandatory tests on the exact tag.
2. Build runtime/frontend assets once and run `comfy node pack`.
3. Install and execute that candidate archive in a clean environment.
4. Require approval before secret access.
5. Publish from the same unchanged workspace; compare the publish-time file manifest because the current CLI repacks before upload.
6. If failure occurs after Registry version creation, treat that version as
   consumed and increment before retrying.
7. Verify the Registry page and install the exact published version.

Do not change source or built assets after approval. Registry immutability makes provenance and publish-manifest verification more important, not less.

## 14. Release checklist

### Version and compatibility

- [ ] Node IDs and serialized schema were compared with the previous release.
- [ ] Breaking changes are major; compatible features are minor; fixes are patch.
- [ ] One version value is authoritative and all displayed metadata agrees.
- [ ] `requires-python`, `requires-comfyui`, frontend constraint, classifiers, and README match tested reality.
- [ ] A bad previous version is deprecated with an upgrade instruction rather than overwritten.

### Dependencies and package

- [ ] Every direct runtime dependency is declared with the least restrictive tested bounds.
- [ ] Platform dependencies use markers.
- [ ] No unnecessary Torch/core-stack pin was introduced.
- [ ] Static `pyproject.toml` dependencies and any compatibility `requirements.txt` agree.
- [ ] `comfy node validate` completed.
- [ ] `comfy node pack` completed.
- [ ] `node.zip` was manually/programmatically inspected.
- [ ] Required built frontend assets are included.
- [ ] Tests, secrets, caches, private assets, and oversized samples are excluded.

### Quality

- [ ] Ruff and tests pass from a clean environment.
- [ ] Root import/registration passes without network or model loading.
- [ ] Representative node behavior, batch, device/dtype, and error cases pass.
- [ ] Schema snapshot/diff was reviewed, including inputs that `node-diff` does not check.
- [ ] The packed release starts in clean ComfyUI.
- [ ] At least one packaged example workflow executes.
- [ ] Minimum and latest stated ComfyUI versions were tested.
- [ ] Applicable OS/accelerator claims were exercised.

### Security and resources

- [ ] No `eval`, `exec`, obfuscation, or runtime subprocess package installation.
- [ ] Routes, paths, URLs, archive extraction, and external data are validated.
- [ ] Network operations are bounded and documented.
- [ ] No secret is committed, logged, returned, or packaged.
- [ ] Long work reports progress and can be interrupted.
- [ ] Files, network responses, temp data, and large tensor/model references are released.
- [ ] Cold/hot cache behavior and representative RAM/VRAM use were checked.
- [ ] GitHub Actions are commit-pinned and token permissions are minimal.

### Documentation and publication

- [ ] README node catalog and compatibility table are current.
- [ ] Embedded help matches stable node IDs.
- [ ] `example_workflows/*.json` and preview images are current.
- [ ] Peer-node/model requirements and migration steps are explicit.
- [ ] Changelog explains user-visible and breaking changes.
- [ ] Release tag/manual approval points to the tested commit.
- [ ] `REGISTRY_ACCESS_TOKEN` is available only to the protected publish job.
- [ ] Automation treats a failed post-creation publish as a consumed version
  and increments before retrying.
- [ ] Registry metadata, downloadable archive, and exact-version installation were verified after publishing.

## 15. Maintenance loop

After release:

- triage reproducible issues with a minimal workflow and environment details;
- test current stable ComfyUI and relevant frontend releases regularly;
- monitor dependency conflicts rather than blindly widening or pinning;
- publish patch releases for fixes because published versions are immutable;
- deprecate unsafe/broken versions with a clear target version;
- preserve old node IDs or ship an explicit migration;
- keep example workflows and embedded help executable;
- rotate/remove unused Registry credentials; and
- announce end-of-support rather than leaving misleading compatibility metadata.

“Actively maintained” does not require accepting every feature request. It does require honest support boundaries, security response, and a clear deprecation path.

## 16. Known upstream inconsistencies and unresolved questions

These should be rechecked before implementing publication automation:

1. **V1/V3 default — transitional.** Core's current example is V3 and migration docs point forward, but the current official cookiecutter still emits V1. V1 remains loaded by core.
2. **`comfy_api.latest` stability — uncertain.** It is the current example import, but “latest” is inherently moving. No audited source justifies treating it as a frozen compatibility promise.
3. **Dependency source — contradictory.** Registry prose/spec shows dynamic `requirements.txt`; current CLI reads static `[project].dependencies`; Manager still supports `requirements.txt`.
4. **License form — transitional.** Current PyPA and comfy-cli use SPDX strings; Registry prose and cookiecutter still show legacy table forms.
5. **Frontend directory metadata — source-only.** Core supports `[tool.comfy].web`; Registry specs do not document it. `WEB_DIRECTORY` remains supported.
6. **Icon dimensions — contradictory.** Registry specification says square `400×400` maximum; publishing initializer prose says `800×400`. Use the stricter spec.
7. **Publishing trigger — divergent examples.** Registry docs publish on a `pyproject.toml` change to `main`; cookiecutter publishes from tags. This guide recommends gated tag/manual publication.
8. **Manager discovery/install path — parallel transition.** Registry says it powers Manager, while current Manager docs still accept list PRs and lifecycle scripts. Do not assume either channel automatically synchronizes all metadata.
9. **Unified dependency resolution — version-gated.** comfy-cli documents Manager `v4.1+` `--uv-compile`; verify the installed Manager behavior before documenting it as required.
10. **Comfy-Action integration — validate locally.** Registry docs promote multi-OS CI, while the action README is oriented to the ComfyUI repository. A node-pack workflow may need adaptation.
11. **`node-diff` coverage — incomplete.** Its own README says input comparison is not implemented; never use it as the sole schema gate.
12. **Issue URL key — contradictory.** `comfy node init` writes
    `"Bug Tracker"`, while the pinned publication parser reads only `Issues`.
    Use `Issues` until those code paths converge.

## Source ledger

Audited on 2026-07-26:

| Project | Revision |
|---|---|
| ComfyUI | `806e092ed42772e4ce7abf44c97c50021cc4bd10` |
| ComfyUI documentation | `089ba2630c7c6a4caab5a686659a2f44b0681f4f` |
| comfy-cli | `85b62da3d660edf13bb3d79ab484aad40cace412` |
| cookiecutter-comfy-extension | `cf4077f11804e009e15b7b399a1b062e317c77e6` |
| ComfyUI-Manager | `9463115e78c64789a6fac2f05f59bda4eabfafbc` |
| node-diff | `f800c0d2e0e7173faf82be60d67eece8ccb5ff7e` |
| publish-node-action | `d2366e7abb6ab16f3bb03e3520ae25c8cf749bc9` |
| comfy-action | `2239a587d36772deab9605f1543abf0dc8aa8f92` |
| registry-backend | `86e4bbc57ec46192be1d22c048208c396b565349` |

[registry-overview]: https://github.com/Comfy-Org/docs/blob/089ba2630c7c6a4caab5a686659a2f44b0681f4f/registry/overview.mdx
[registry-publishing]: https://github.com/Comfy-Org/docs/blob/089ba2630c7c6a4caab5a686659a2f44b0681f4f/registry/publishing.mdx
[registry-spec]: https://github.com/Comfy-Org/docs/blob/089ba2630c7c6a4caab5a686659a2f44b0681f4f/registry/specifications.mdx
[registry-standards]: https://github.com/Comfy-Org/docs/blob/089ba2630c7c6a4caab5a686659a2f44b0681f4f/registry/standards.mdx
[registry-cicd]: https://github.com/Comfy-Org/docs/blob/089ba2630c7c6a4caab5a686659a2f44b0681f4f/registry/cicd.mdx
[docs-walkthrough]: https://github.com/Comfy-Org/docs/blob/089ba2630c7c6a4caab5a686659a2f44b0681f4f/custom-nodes/walkthrough.mdx
[docs-v3]: https://github.com/Comfy-Org/docs/blob/089ba2630c7c6a4caab5a686659a2f44b0681f4f/custom-nodes/v3_migration.mdx
[docs-lazy]: https://github.com/Comfy-Org/docs/blob/089ba2630c7c6a4caab5a686659a2f44b0681f4f/custom-nodes/backend/lazy_evaluation.mdx
[docs-lists]: https://github.com/Comfy-Org/docs/blob/089ba2630c7c6a4caab5a686659a2f44b0681f4f/custom-nodes/backend/lists.mdx
[docs-expansion]: https://github.com/Comfy-Org/docs/blob/089ba2630c7c6a4caab5a686659a2f44b0681f4f/custom-nodes/backend/expansion.mdx
[docs-manager]: https://github.com/Comfy-Org/docs/blob/089ba2630c7c6a4caab5a686659a2f44b0681f4f/custom-nodes/backend/manager.mdx
[docs-js]: https://github.com/Comfy-Org/docs/blob/089ba2630c7c6a4caab5a686659a2f44b0681f4f/custom-nodes/js/javascript_overview.mdx
[docs-help]: https://github.com/Comfy-Org/docs/blob/089ba2630c7c6a4caab5a686659a2f44b0681f4f/custom-nodes/help_page.mdx
[docs-workflows]: https://github.com/Comfy-Org/docs/blob/089ba2630c7c6a4caab5a686659a2f44b0681f4f/custom-nodes/workflow_templates.mdx
[docs-subgraphs]: https://github.com/Comfy-Org/docs/blob/089ba2630c7c6a4caab5a686659a2f44b0681f4f/custom-nodes/subgraph_blueprints.mdx
[docs-i18n]: https://github.com/Comfy-Org/docs/blob/089ba2630c7c6a4caab5a686659a2f44b0681f4f/custom-nodes/i18n.mdx
[core-pyproject]: https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/pyproject.toml
[core-loader]: https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/nodes.py
[core-v3-example]: https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/custom_nodes/example_node.py.example
[core-workflow-scanner]: https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/app/custom_node_manager.py
[core-subgraph-scanner]: https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/app/subgraph_manager.py
[core-model-management]: https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy/model_management.py
[core-readme]: https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/README.md
[template-pyproject]: https://github.com/Comfy-Org/cookiecutter-comfy-extension/blob/cf4077f11804e009e15b7b399a1b062e317c77e6/%7B%7Bcookiecutter.project_slug%7D%7D/common/pyproject.toml
[template-init]: https://github.com/Comfy-Org/cookiecutter-comfy-extension/blob/cf4077f11804e009e15b7b399a1b062e317c77e6/%7B%7Bcookiecutter.project_slug%7D%7D/custom-nodes-template/__init__.py
[template-nodes]: https://github.com/Comfy-Org/cookiecutter-comfy-extension/blob/cf4077f11804e009e15b7b399a1b062e317c77e6/%7B%7Bcookiecutter.project_slug%7D%7D/custom-nodes-template/src/%7B%7Bcookiecutter.project_slug%7D%7D/nodes.py
[template-ci]: https://github.com/Comfy-Org/cookiecutter-comfy-extension/blob/cf4077f11804e009e15b7b399a1b062e317c77e6/%7B%7Bcookiecutter.project_slug%7D%7D/custom-nodes-template/.github/workflows/build-pipeline.yml
[template-test]: https://github.com/Comfy-Org/cookiecutter-comfy-extension/blob/cf4077f11804e009e15b7b399a1b062e317c77e6/%7B%7Bcookiecutter.project_slug%7D%7D/custom-nodes-template/tests/test_%7B%7Bcookiecutter.project_slug%7D%7D.py
[cli-readme]: https://github.com/Comfy-Org/comfy-cli/blob/85b62da3d660edf13bb3d79ab484aad40cace412/README.md
[cli-config-parser]: https://github.com/Comfy-Org/comfy-cli/blob/85b62da3d660edf13bb3d79ab484aad40cace412/comfy_cli/registry/config_parser.py
[cli-node-command]: https://github.com/Comfy-Org/comfy-cli/blob/85b62da3d660edf13bb3d79ab484aad40cace412/comfy_cli/command/custom_nodes/command.py
[cli-file-utils]: https://github.com/Comfy-Org/comfy-cli/blob/85b62da3d660edf13bb3d79ab484aad40cace412/comfy_cli/file_utils.py
[manager-core]: https://github.com/Comfy-Org/ComfyUI-Manager/blob/9463115e78c64789a6fac2f05f59bda4eabfafbc/glob/manager_core.py
[manager-readme]: https://github.com/Comfy-Org/ComfyUI-Manager/blob/9463115e78c64789a6fac2f05f59bda4eabfafbc/README.md
[node-diff]: https://github.com/Comfy-Org/node-diff/blob/f800c0d2e0e7173faf82be60d67eece8ccb5ff7e/README.md
[publish-action-source]: https://github.com/Comfy-Org/publish-node-action/blob/d2366e7abb6ab16f3bb03e3520ae25c8cf749bc9/action.yml
[comfy-action]: https://github.com/Comfy-Org/comfy-action/blob/2239a587d36772deab9605f1543abf0dc8aa8f92/README.md
[react-template]: https://github.com/Comfy-Org/ComfyUI-React-Extension-Template
[security-discussion]: https://github.com/Comfy-Org/ComfyUI/discussions/1219
[pypa-pyproject]: https://packaging.python.org/en/latest/specifications/pyproject-toml/
[pypa-dependencies]: https://packaging.python.org/en/latest/specifications/dependency-specifiers/
[pep639]: https://peps.python.org/pep-0639/
[setuptools-pyproject]: https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html
[registry-backend-version]: https://github.com/Comfy-Org/registry-backend/blob/86e4bbc57ec46192be1d22c048208c396b565349/services/registry/registry_svc.go#L460-L539
[github-actions-security]: https://docs.github.com/en/actions/reference/security/secure-use
