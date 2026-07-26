# ComfyUI custom-node backend API

> - Research snapshot: **2026-07-26**
> - ComfyUI source audited at [`806e092ed42772e4ce7abf44c97c50021cc4bd10`](https://github.com/Comfy-Org/ComfyUI/commit/806e092ed42772e4ce7abf44c97c50021cc4bd10)
> - Official docs source audited at [`089ba2630c7c6a4caab5a686659a2f44b0681f4f`](https://github.com/Comfy-Org/docs/tree/089ba2630c7c6a4caab5a686659a2f44b0681f4f)

This is an implementation reference for writing Python custom nodes against current ComfyUI. It covers discovery, registration, the legacy V1 class contract, the experimental V3 schema contract, execution, validation, caching, lazy evaluation, hidden inputs, data types, list processing, tensor batches, and the minimum frontend/server-extension surface a backend node author needs to understand.

## Status vocabulary used here

- **Legacy-supported**: described as legacy by the V3 migration guide, but still implemented by the current loader and executor. This is the status of V1 nodes.
- **Current experimental**: present in current source and official documentation, but explicitly not marked stable. This is the status of the usable V3 API.
- **Deprecated**: explicitly marked deprecated in source or official docs.
- **Source-only**: implemented in the audited source but not established as a public, documented compatibility contract.

“Current” in this document means the pinned source snapshot above. It does not promise that an unpinned future checkout will behave identically.

## Executive decision

There are two supported registration shapes today:

| Goal | Recommended API | Reason |
|---|---|---|
| Broad compatibility with existing ComfyUI installs | **V1** | The current loader and executor still support it fully, without requiring the experimental V3 API. |
| Use new schema capabilities such as `MultiType`, `MatchType`, dynamic inputs, or the newer extension lifecycle | **V3** | These features belong to the new API, but the usable V3 packages are currently experimental. |
| Publish one package that supports both generations | Prefer a V1 implementation first; add an intentionally separated compatibility layer only after a real need appears | A module exporting both V1 and V3 registration hooks does **not** register both: current loading gives V1 precedence. |

The official V3 migration guide says that future node features will target V3, and the repository’s current example node uses `comfy_api.latest`. However, the audited source marks both `latest` and `v0_0_2` as `STABLE = False`; `v0_0_1` is marked stable only as a template that its own comment says nobody should use. There is therefore **no usable stable V3 version in this snapshot**. See the [V3 maturity warning](#31-v3-maturity-warning) before choosing it.

For a new node suite whose requirements do not demand V3-only functionality, V1 is the conservative starting point. Do not create parallel V1/V3 implementations speculatively.

## 1. Discovery and registration

### 1.1 What ComfyUI scans

The default custom-node root is `<ComfyUI base>/custom_nodes`. Additional `custom_nodes` paths can be configured through ComfyUI’s path configuration. The default is set in [`folder_paths.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/folder_paths.py#L14-L45).

At startup, ComfyUI enumerates each configured custom-node root and considers:

- a top-level `.py` file; or
- a directory, imported through that directory’s `__init__.py`.

Non-Python files are ignored, entries ending in `.disabled` are skipped, and disabled/blocked packages can be filtered by command-line or manager policy. Import failures are logged and do not normally stop every other custom node from loading. See the current scan and import implementation in [`nodes.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/nodes.py#L2227-L2371) and the concise official [custom-node lifecycle](https://docs.comfy.org/custom-nodes/backend/lifecycle).

Importing is executable startup work: top-level Python code runs during ComfyUI startup. Keep imports fast and side-effect-light. Defer model loading, device allocation, network access, and other expensive initialization until actually needed.

Runtime discovery is a filesystem scan, not Python package-entry-point discovery. Registry or `pyproject.toml` metadata can help installation and publication, but does not itself register node classes.

### 1.2 Registration selection and precedence

After importing a module, the loader checks in this order:

1. If `NODE_CLASS_MAPPINGS` exists and is not `None`, register it as V1.
2. `elif` the module has callable `comfy_entrypoint`, load it as V3.
3. Otherwise, skip the module.

That precedence is explicit in [`load_custom_node`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/nodes.py#L2275-L2316). Consequences:

- Do **not** export both `NODE_CLASS_MAPPINGS` and `comfy_entrypoint` from the same imported module. V1 wins and V3 is ignored.
- `__all__` is a useful package convention, but the loader does not inspect it when deciding whether or how to register the module.
- Node IDs share a global registry. Core IDs are protected during custom-node loading, but custom packages can collide with each other and later registration can replace an earlier custom entry. Prefix every node ID with a package-specific identifier.

Example IDs:

```text
LFGG_ImageMetadata
LFGG_BatchSelect
LFGG_PromptTemplate
```

Treat the ID as serialized API surface. Workflows store it in each API prompt’s `class_type`; changing it breaks old workflows unless a migration/replacement strategy is provided.

### 1.3 Suggested package layout

```text
comfyui-lfgg-nodes/
├── __init__.py
├── nodes/
│   ├── __init__.py
│   ├── image.py
│   └── text.py
├── pyproject.toml
└── web/                 # only if frontend behavior is genuinely needed
    └── lfgg.js
```

The root `__init__.py` should expose exactly one registration generation. The implementation can be split into internal modules without changing how ComfyUI discovers the package.

### 1.4 Display names

V1 may export `NODE_DISPLAY_NAME_MAPPINGS`, a mapping from serialized node ID to user-facing name. V3 places the user-facing name in `Schema.display_name`. The ID and display name serve different purposes: keep the ID stable and change only the display name when making cosmetic naming improvements.

## 2. V1 node contract — legacy-supported

The current server still models V1 nodes as Python classes whose class attributes describe the graph interface and whose named method performs execution. The official [server overview](https://docs.comfy.org/custom-nodes/backend/server_overview) is the public contract; current type definitions are visible in [`comfy/comfy_types/node_typing.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy/comfy_types/node_typing.py#L197-L320).

### 2.1 Minimal V1 node

```python
class LFGGAdd:
    CATEGORY = "LFGG/Math"
    DESCRIPTION = "Add two integer values."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "left": ("INT", {"default": 0}),
                "right": ("INT", {"default": 0}),
            }
        }

    RETURN_TYPES = ("INT",)
    RETURN_NAMES = ("sum",)
    FUNCTION = "execute"

    def execute(self, left, right):
        return (left + right,)


NODE_CLASS_MAPPINGS = {
    "LFGG_Add": LFGGAdd,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LFGG_Add": "LFGG Add",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
```

Important Python details:

- `RETURN_TYPES` is always a tuple. One output is `("INT",)`, not `("INT")`.
- Ordinary execution returns a tuple aligned with `RETURN_TYPES`. One output is
  `(value,)`; nodes returning UI or expansion data may instead use the
  documented dictionary envelope described in
  [§4.1](#41-output-return-shape-and-ui-data).
- A node with no graph outputs uses `RETURN_TYPES = ()` and returns `()`.
- Inputs are passed by **keyword name**, so the execution method’s parameters must match the schema’s input names unless it deliberately accepts `**kwargs`.

### 2.2 Core V1 attributes and methods

| Member | Required? | Meaning |
|---|---:|---|
| `INPUT_TYPES()` | Yes | `@classmethod` returning input declarations under `required`, and optionally `optional` and `hidden`. Use `{"required": {}}` if there are no ordinary inputs. |
| `RETURN_TYPES` | Yes | Tuple of output type IDs, in socket order. Use `()` for none. |
| `FUNCTION` | Yes | String naming the method ComfyUI invokes. |
| `execute(...)` or named equivalent | Yes | Receives resolved inputs as keyword arguments and returns output values. The function name is arbitrary as long as `FUNCTION` matches. |
| `CATEGORY` | Recommended | Slash-delimited Add Node menu path, for example `"LFGG/Image"`. |
| `RETURN_NAMES` | Optional | Tuple of user-facing output labels aligned with `RETURN_TYPES`. |
| `OUTPUT_NODE` | Optional, default false | Makes the node an execution target/root. It does not mean the node must have zero outputs. |
| `INPUT_IS_LIST` | Optional, default false | Sends every input to one invocation as a list instead of applying normal element-wise list mapping. |
| `OUTPUT_IS_LIST` | Optional | Tuple aligned with `RETURN_TYPES`; marks outputs as ComfyUI scheduling lists rather than ordinary values. |
| `VALIDATE_INPUTS` | Optional | Custom prompt validation hook. |
| `IS_CHANGED` | Optional | Adds an external-state fingerprint to the cache signature. It is not a boolean “changed?” callback. |
| `check_lazy_status` | Required only for lazy inputs | Selects which unresolved lazy inputs need evaluation. |
| `DESCRIPTION` | Optional | User-facing node description/tooltip. |
| `SEARCH_ALIASES` | Optional | Alternative search terms. |
| `DEPRECATED`, `EXPERIMENTAL`, `DEV_ONLY` | Optional flags | Frontend/status metadata. |

`OUTPUT_NODE = True` causes validation/execution to select the node as an output target and traverse its dependencies. Nodes that are not on a path to a selected target do not execute. Output targets still participate in caching; the executor checks the output cache before invoking them. The selection code is in [`execution.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/execution.py#L1139-L1167), while the cache-before-call path is in the same file’s [node execution logic](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/execution.py#L436-L449).

### 2.3 Input declaration grammar

`INPUT_TYPES()` returns:

```python
{
    "required": {
        "count": ("INT", {"default": 1, "min": 1, "max": 100}),
    },
    "optional": {
        "label": ("STRING", {"default": "", "multiline": False}),
    },
    "hidden": {
        "node_id": "UNIQUE_ID",
    },
}
```

Each ordinary entry is generally:

```python
"parameter_name": ("TYPE_ID", {options})
```

The options dictionary is optional:

```python
"image": ("IMAGE",)
```

Common options include:

| Option | Applies to | Notes |
|---|---|---|
| `default` | widget-backed inputs | Initial value. |
| `min`, `max`, `step` | `INT`, `FLOAT` | Server validates literal bounds for the built-in numeric types; `step` is chiefly widget behavior. |
| `round` | `FLOAT` | Frontend numeric rounding metadata. |
| `multiline`, `placeholder`, `dynamicPrompts` | `STRING` | Text widget behavior. |
| `label_on`, `label_off` | `BOOLEAN` | Display labels. |
| `forceInput` | widget-capable input | Forces a socket instead of relying on a widget. Particularly useful for optional inputs. |
| `lazy` | any input | Leaves the upstream value unresolved until `check_lazy_status` requests it. |
| `rawLink` | linked input | Passes the raw `[node_id, output_index]` link instead of evaluating it; designed for graph expansion. |
| `tooltip` | input | Hover help. |
| `socketless` | widget-capable input | Prevents a socket when the widget exists; requires frontend 1.17.5 or later. |
| `widgetType` | widget-capable input | Uses a different widget initialization type; requires frontend 1.18.0 or later. |

The authoritative current option typing, including frontend-version notes, is in [`InputTypeOptions`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy/comfy_types/node_typing.py#L96-L179). Frontend-sensitive options should be paired with a documented minimum frontend version.

`defaultInput` is **deprecated** in frontend 1.16 and later. For required inputs, remove it; for optional inputs that must be sockets, use `forceInput`. That deprecation is recorded directly in the current [type definition](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy/comfy_types/node_typing.py#L106-L116).

Optional inputs may be absent entirely from the API prompt. Their execution parameters therefore need Python defaults or must be collected safely:

```python
def execute(self, image, mask=None):
    ...
```

### 2.4 Combo inputs

Two representations exist:

```python
# Current explicit form
"mode": ("COMBO", {"options": ["fast", "quality"]})

# Longstanding list-first form
"mode": (["fast", "quality"],)
```

The list-first representation remains understood by current validation/execution, but current source labels it outdated and prefers an explicit `COMBO` type with `options`; see [`InputTypeOptions.options`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy/comfy_types/node_typing.py#L167-L176), the outdated-format note in [`comfy_execution/graph.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy_execution/graph.py#L99-L103), and both formats being checked by current [`execution.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/execution.py#L1040-L1049). Use the explicit form when targeting current ComfyUI; use the old form only if tests demonstrate a required older-version compatibility boundary.

## 3. V3 schema API — current experimental

V3 replaces scattered V1 class attributes with typed schema objects, makes execution a classmethod, and registers nodes through a `ComfyExtension`. The official [V3 migration guide](https://docs.comfy.org/custom-nodes/v3_migration) is the main public guide, while the repository’s live example is [`custom_nodes/example_node.py.example`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/custom_nodes/example_node.py.example#L1-L130).

### 3.1 V3 maturity warning

At the audited commit:

- `comfy_api.latest` declares `STABLE = False` in [`comfy_api/latest/__init__.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy_api/latest/__init__.py#L18-L20).
- `comfy_api.v0_0_2` also declares `STABLE = False` and re-exports `io`, `ui`, and `ComfyExtension` from `latest`; see [`v0_0_2/__init__.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy_api/v0_0_2/__init__.py#L1-L15).
- `v0_0_1` says it exists only as an adapter template and “there is no reason anyone should ever use it,” even though it sets `STABLE = True`; see [`v0_0_1/__init__.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy_api/v0_0_1/__init__.py#L11-L15).
- The supported-version list contains only those three variants in [`version_list.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy_api/version_list.py#L1-L10).

This conflicts with language in the migration documentation that implies a previous V3 version can be treated as stable. For this snapshot, the source flags are decisive: **V3 is usable but experimental, and pinning `v0_0_2` does not create an independently stable schema layer**.

If V3 is selected:

1. Declare a minimum tested ComfyUI version or commit.
2. Test against that floor and current ComfyUI.
3. Expect migration work.
4. Re-audit version stability before release.
5. Do not import `v0_0_1`.

### 3.2 Minimal V3 node and extension

```python
from typing_extensions import override

from comfy_api.latest import ComfyExtension, io


class LFGGAdd(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="LFGG_Add",
            display_name="LFGG Add",
            category="LFGG/Math",
            description="Add two integer values.",
            inputs=[
                io.Int.Input("left", default=0),
                io.Int.Input("right", default=0),
            ],
            outputs=[
                io.Int.Output("sum"),
            ],
        )

    @classmethod
    def execute(cls, left: int, right: int) -> io.NodeOutput:
        return io.NodeOutput(left + right)


class LFGGExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [LFGGAdd]


async def comfy_entrypoint() -> LFGGExtension:
    return LFGGExtension()
```

Do not also export `NODE_CLASS_MAPPINGS` from this module.

`comfy_entrypoint` may be synchronous or asynchronous. It must return a `ComfyExtension`. The loader awaits `extension.on_load()` and then `extension.get_node_list()`, which must return a list of V3 node classes. This behavior is implemented in the V3 branch of [`load_custom_node`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/nodes.py#L2290-L2315).

Use `on_load` only for extension-wide setup that must happen at load time. Prefer lazy initialization for expensive resources.

### 3.3 V1-to-V3 mapping

| V1 | V3 |
|---|---|
| `NODE_CLASS_MAPPINGS` | `ComfyExtension.get_node_list()` returned through `comfy_entrypoint` |
| `NODE_DISPLAY_NAME_MAPPINGS` | `Schema.display_name` |
| `INPUT_TYPES()` | `Schema.inputs` containing `io.*.Input` objects |
| `RETURN_TYPES` | `Schema.outputs` containing `io.*.Output` objects |
| `RETURN_NAMES` | Output object IDs/display names |
| `FUNCTION` | Fixed `execute` classmethod |
| `CATEGORY` | `Schema.category` |
| `DESCRIPTION` | `Schema.description` |
| `OUTPUT_NODE` | `Schema.is_output_node` |
| `INPUT_IS_LIST` | `Schema.is_input_list` |
| `OUTPUT_IS_LIST` | `io.*.Output(..., is_output_list=True)` |
| `VALIDATE_INPUTS` | `validate_inputs` classmethod |
| `IS_CHANGED` | `fingerprint_inputs` classmethod |
| `check_lazy_status` | `check_lazy_status` classmethod |
| V1 `hidden` dictionary | `Schema.hidden` and values on `cls.hidden` |

V3 schemas are translated into the V1-shaped node metadata currently consumed by server routes and the frontend. The adapter is visible in [`Schema.get_v1_info`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy_api/latest/_io.py#L1711-L1765). This explains why both generations appear through the same `/object_info` endpoint; it does not make V3 stable.

### 3.4 Important `Schema` fields

Current `Schema` fields are defined in [`comfy_api/latest/_io.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy_api/latest/_io.py#L1587-L1653):

| Field | Meaning |
|---|---|
| `node_id` | Globally unique serialized node ID. Prefix it. |
| `display_name` | User-facing label. |
| `category` | Slash-delimited menu category. |
| `inputs`, `outputs` | Typed input/output objects. |
| `hidden` | Requested hidden context values. |
| `description`, `search_aliases` | Discovery/help metadata. |
| `is_input_list` | Receive all inputs as lists in one call. |
| `is_output_node` | Select as an execution target/root. |
| `is_deprecated`, `is_experimental`, `is_dev_only` | Status/visibility metadata. |
| `not_idempotent` | Include node ID in the input signature so *different graph nodes* with identical inputs do not share outputs. It does not force the same node to run every queue. |
| `enable_expand` | Allows `NodeOutput` to include a graph expansion. |
| `accept_all_inputs` | Pass prompt inputs that are not declared in the schema through `**kwargs`; use narrowly because it weakens the visible contract. |
| `has_intermediate_output` | Persist/resend UI output while remaining dependent on a real output node; it does not make this node an execution root. |

The source also contains service-specific API-node and pricing fields. Ordinary local custom nodes should not opt into API-node authentication fields or handle ComfyOrg credentials unless they are deliberately implementing that contract.

### 3.5 Inputs and outputs

Common V3 input metadata—ID, display name, optionality, tooltip, laziness, raw-link behavior, and widget settings—is defined by the current [`Input` and `WidgetInput` base classes](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy_api/latest/_io.py#L142-L230).

Examples:

```python
io.Image.Input("image")
io.Mask.Input("mask", optional=True)
io.Int.Input("seed", default=0, min=0, max=2**63 - 1)
io.Float.Input("strength", default=1.0, min=0.0, max=1.0, step=0.01)
io.String.Input("prompt", multiline=True, default="")
io.Combo.Input("mode", options=["fast", "quality"])
```

For a package-specific wire type:

```python
LFGG_METADATA = io.Custom("LFGG_METADATA")

# In schemas:
LFGG_METADATA.Input("metadata")
LFGG_METADATA.Output("metadata")
```

`io.Custom` creates a type with the provided socket ID; see its current definition in [`_io.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy_api/latest/_io.py#L133-L138). Prefix custom types just like node IDs.

V3 also exposes advanced `MultiType`, `MatchType`, autogrowing inputs, and dynamic combo/input facilities. They are legitimate current features but inherit the overall experimental V3 status. Use them only when the graph contract genuinely needs dynamic or polymorphic sockets; prefer a concrete type otherwise.

Return `io.NodeOutput(...)` with values aligned to the schema’s outputs:

```python
return io.NodeOutput(result_image, metadata)
```

`NodeOutput` also carries `ui`, `expand`, and `block_execution` data in the current implementation; expansion must be enabled by `Schema.enable_expand`. See [`NodeOutput`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy_api/latest/_io.py#L2226-L2245). The executor still normalizes some legacy return shapes, but V3 code should use `NodeOutput`.

### 3.6 V3 is class-based, not instance-state-based

V3 `execute`, `validate_inputs`, `fingerprint_inputs`, and `check_lazy_status` are classmethods. During execution ComfyUI uses a sanitized shallow class clone and attaches hidden context to it. An instance `__init__` and instance fields therefore do not implement durable per-node state. The relevant V3 class contract is in [`ComfyNode`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy_api/latest/_io.py#L1859-L1980), and the executor’s class preparation is in [`execution.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/execution.py#L271-L305).

Keep graph-visible behavior determined by declared inputs. For expensive shared resources, use a deliberate module/extension cache with bounded lifetime and explicit invalidation rather than accidental object state.

## 4. Execution lifecycle

The practical lifecycle is:

1. **Startup discovery**: ComfyUI imports custom-node modules and registers V1 mappings or V3 extension classes.
2. **Metadata exposure**: `/object_info` serializes every registered node’s schema for the client. Current routes are implemented in [`server.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/server.py#L741-L809).
3. **Prompt submission**: the client sends an API prompt in which each graph node has a node ID, a `class_type`, and `inputs`.
4. **Validation**: `/prompt` calls prompt validation before queueing. The current request path is in [`server.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/server.py#L1062-L1115).
5. **Target selection**: output nodes, or explicit partial-execution targets, determine the required dependency subgraph.
6. **Cache setup and scheduling**: the executor computes signatures and schedules dependencies before consumers.
7. **Input resolution**: literal values, linked upstream outputs, hidden values, lazy values, and list mapping are prepared.
8. **Node call**: V1 invokes the method named by `FUNCTION`; V3 invokes the classmethod `execute`. The executor runs inside PyTorch inference mode.
9. **Normalization and storage**: graph outputs, UI output, expansion data, blockers, and cache entries are normalized and stored.

Prompt execution and cache initialization can be followed in [`execution.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/execution.py#L727-L820); input preparation and list-mapped function invocation are in the same file at [`#L157-L317`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/execution.py#L157-L317).

V1 classes are instantiated and cached by graph node ID during execution, but code should not rely on those instances as permanent application storage; execution/caches can be reset. V3 intentionally exposes a stateless classmethod contract.

### 4.1 Output return shape and UI data

Ordinary V1 graph data is returned as a tuple:

```python
return (image, metadata)
```

Legacy output/UI nodes may return a dictionary shaped like:

```python
return {
    "ui": {"images": preview_descriptors},
    "result": (image,),
}
```

V3 should use:

```python
return io.NodeOutput(image, ui={"images": preview_descriptors})
```

Do not put large tensor payloads into UI dictionaries. Graph outputs stay in the backend execution/cache path; UI output should contain small serializable descriptors or values needed by the client.

## 5. Validation

ComfyUI validates the submitted **prompt representation**, not arbitrary runtime objects that have not yet executed.

### 5.1 Default validation

Current validation checks, among other things:

- required inputs are present;
- linked socket types are compatible;
- literal built-in primitives can be converted to the declared type;
- literal numeric values satisfy `min` and `max`;
- literal combo values belong to the available options.

The validation implementation is in [`execution.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/execution.py#L891-L1073).

Frontend link checks are useful feedback, but they are not a security boundary. The backend accepts API prompts from clients other than the browser, so nodes must validate filesystem paths, URLs, enum values, sizes, and other trust-boundary data themselves.

### 5.2 Custom validation hook

V1:

```python
@classmethod
def VALIDATE_INPUTS(cls, width):
    if width % 8 != 0:
        return "width must be divisible by 8"
    return True
```

V3:

```python
@classmethod
def validate_inputs(cls, width):
    if width % 8 != 0:
        return "width must be divisible by 8"
    return True
```

Return `True` when valid. Return an explanatory string when invalid; returning `False` produces a less useful generic failure.

The executor chooses `validate_inputs` for V3 and `VALIDATE_INPUTS` for V1, then inspects the method signature; see [`execution.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/execution.py#L863-L889).

Critical behavior:

- Custom validation receives literal prompt values. It does not execute upstream nodes just to obtain linked values.
- A linked input requested by name may be unavailable as a runtime value during validation.
- A special `input_types` argument can inspect declared upstream types.
- Required-input checks and built-in primitive conversion still occur before the custom hook.
- If the validator explicitly names a literal input, ComfyUI skips the built-in `min`/`max`/combo-membership checks for that input.
- If it accepts `**kwargs`, those built-in literal constraint checks are skipped for all supplied schema inputs.
- Requesting `input_types` takes responsibility for linked socket-type validation.

These rules are documented under [custom validation](https://docs.comfy.org/custom-nodes/backend/more_on_inputs) and implemented around [`validate_node_input`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/execution.py#L930-L1103). A custom validator is therefore a replacement for the relevant constraint checks, not merely an additive callback. Re-implement every constraint that matters for the parameters it captures.

### 5.3 Wildcard inputs are a workaround

The `"*"`/`IO.ANY` type is an escape hatch, not a fully supported universal socket. Current type source warns that it causes reroute and link-type issues and should be avoided where possible; see [`IO.ANY`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy/comfy_types/node_typing.py#L16-L71). Prefer concrete types, a prefixed custom type, or V3 `MultiType`/`MatchType` when those experimental features are acceptable.

## 6. Caching and change detection

### 6.1 Default cache signature

For deterministic nodes whose behavior is entirely a function of declared graph inputs, no custom cache hook is needed.

The current input-signature cache includes:

- node class/type;
- the value from `IS_CHANGED` or `fingerprint_inputs`, if present;
- literal input values;
- linked ancestor structure and output indices;
- an ordered signature of the full ancestry.

The current algorithm is in [`comfy_execution/caching.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy_execution/caching.py#L82-L148). Different cache storage policies can retain or evict entries differently, but the node contract should not depend on a particular retention policy.

The cache cannot infer undeclared dependencies such as:

- a file’s content changing while its path string stays the same;
- environment variables;
- remote responses;
- global mutable state;
- wall-clock time;
- a model/resource selected outside graph inputs.

Represent such dependencies as explicit inputs where practical. Otherwise fingerprint them.

### 6.2 `IS_CHANGED` / `fingerprint_inputs`

Despite the V1 name, `IS_CHANGED` does not return a boolean answer to “did it change?” It returns a **fingerprint** that becomes part of the signature.

V1:

```python
@classmethod
def IS_CHANGED(cls, path):
    return compute_file_hash(path)
```

V3:

```python
@classmethod
def fingerprint_inputs(cls, path):
    return compute_file_hash(path)
```

Rules:

- Same fingerprint and same graph signature can reuse the cache.
- Different fingerprint invalidates the cached output.
- Returning constant `True` does **not** force execution; it is the same fingerprint every time.
- `float("NaN")` is the conventional always-miss fingerprint because NaN does not compare equal to itself.
- A fingerprint exception is currently treated as an always-changing value, but nodes should report failures deliberately rather than rely on that fallback.
- Like validation, fingerprinting operates before linked values are evaluated; design it primarily around literal inputs or hidden context.

Current fingerprint lookup is implemented by `IsChangedCache` in [`execution.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/execution.py#L58-L99).

For randomness, prefer an explicit `seed` input. A seed makes the workflow reproducible and naturally participates in the signature. Use an always-miss fingerprint only for a node whose actual contract is “perform an external side effect/effectively new read every queue.”

### 6.3 Node identity is not “always execute”

V1 nodes requesting hidden `UNIQUE_ID`, and V3 schemas with `not_idempotent=True`, include the graph node ID in the signature. That stops two distinct graph nodes with otherwise identical signatures from sharing results. It does **not** make the same graph node run again when its inputs have not changed. The behavior is visible in [`comfy_execution/caching.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy_execution/caching.py#L19-L24) and [`#L109-L127`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy_execution/caching.py#L109-L127).

## 7. Hidden inputs

Hidden inputs provide execution context without creating visible sockets/widgets.

### 7.1 V1

```python
@classmethod
def INPUT_TYPES(cls):
    return {
        "required": {},
        "hidden": {
            "node_id": "UNIQUE_ID",
            "prompt": "PROMPT",
            "metadata": "EXTRA_PNGINFO",
            "dynprompt": "DYNPROMPT",
        },
    }

def execute(self, node_id, prompt, metadata, dynprompt):
    ...
```

### 7.2 V3

```python
@classmethod
def define_schema(cls):
    return io.Schema(
        node_id="LFGG_ContextExample",
        inputs=[],
        outputs=[],
        hidden=[
            io.Hidden.unique_id,
            io.Hidden.prompt,
            io.Hidden.extra_pnginfo,
            io.Hidden.dynprompt,
        ],
    )

@classmethod
def execute(cls):
    node_id = cls.hidden.unique_id
    prompt = cls.hidden.prompt
    metadata = cls.hidden.extra_pnginfo
    dynprompt = cls.hidden.dynprompt
    return io.NodeOutput()
```

Current hidden values are defined in [`comfy_api/latest/_io.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy_api/latest/_io.py#L1435-L1494):

| Hidden value | Meaning |
|---|---|
| `UNIQUE_ID` | This graph node’s serialized ID. Useful for node-specific messages; also affects cache identity. |
| `PROMPT` | The submitted API prompt representation. Treat it as read-only unless a documented operation says otherwise. |
| `EXTRA_PNGINFO` | Metadata supplied for output files/workflows. It may be absent when metadata saving is disabled. |
| `DYNPROMPT` | The mutable dynamic graph used by node expansion. |

The executor injects hidden values during input preparation in [`execution.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/execution.py#L190-L224).

Do not request hidden context by habit. It enlarges the implicit contract, and `UNIQUE_ID` changes cache sharing behavior. Request only what the node uses.

## 8. Lazy evaluation

Normal linked inputs execute before their consumer. A lazy input lets the consumer decide at runtime whether that dependency is needed.

Declare it:

```python
@classmethod
def INPUT_TYPES(cls):
    return {
        "required": {
            "condition": ("BOOLEAN",),
            "when_true": ("IMAGE", {"lazy": True}),
            "when_false": ("IMAGE", {"lazy": True}),
        }
    }
```

Then request only the required unresolved branch:

```python
def check_lazy_status(
    self,
    condition,
    when_true=None,
    when_false=None,
):
    needed = "when_true" if condition else "when_false"
    value = when_true if condition else when_false
    return [needed] if value is None else []
```

V3 uses the same decision model but implements `check_lazy_status` as a classmethod.

Behavior:

- Unevaluated lazy values arrive as `None` (with list-mode details following list semantics).
- Return a list of unresolved input names that are actually required.
- ComfyUI evaluates those dependencies and may call `check_lazy_status` again.
- Return `[]` when no more inputs are needed.
- The eventual execution method sees only values that were requested/evaluated; code must tolerate unselected inputs remaining `None`.

The official [lazy evaluation guide](https://docs.comfy.org/custom-nodes/backend/lazy_evaluation) includes conditional examples, and the current request/retry loop is in [`execution.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/execution.py#L495-L518).

For conditional dataflow, prefer lazy inputs to executing both expensive branches and discarding one. `ExecutionBlocker` and graph expansion are advanced alternatives for blocking or constructing flows; use the official [node expansion guide](https://docs.comfy.org/custom-nodes/backend/expansion) before adopting them.

## 9. Data types

### 9.1 Socket type IDs are graph wire labels

Input and output types are string identifiers used for socket compatibility and metadata. They are not a substitute for Python runtime validation.

Common built-ins include:

```text
STRING  BOOLEAN  INT  FLOAT  COMBO
IMAGE   MASK     LATENT
MODEL   CLIP     VAE     CONDITIONING
AUDIO   VIDEO
```

The current V1 enum contains more core IDs in [`node_typing.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy/comfy_types/node_typing.py#L16-L71), while the official [data types guide](https://docs.comfy.org/custom-nodes/backend/datatypes) explains the general mechanism.

Use a package-prefixed uppercase ID for a custom Python payload:

```python
RETURN_TYPES = ("LFGG_METADATA",)

@classmethod
def INPUT_TYPES(cls):
    return {
        "required": {
            "metadata": ("LFGG_METADATA", {"forceInput": True}),
        }
    }
```

The object sent at runtime can be any Python value agreed upon by producer and consumer. Keep the object contract small, documented, and versionable. Avoid leaking internal mutable objects if downstream nodes can unexpectedly modify them.

Treat `MODEL`, `CLIP`, `VAE`, `CONDITIONING`, and similar core objects as opaque ComfyUI domain objects unless a documented API requires a specific operation. Their internal implementation can evolve.

### 9.2 Images, masks, and latents

Current documented tensor conventions:

| Type | Typical representation | Important handling rule |
|---|---|---|
| `IMAGE` | `torch.Tensor` shaped `[B, H, W, C]`, normally floating point in `[0, 1]` | Channel-last. Preserve batch dimension. |
| `MASK` | `torch.Tensor` canonically `[B, H, W]`; a single mask may appear as `[H, W]` | Normalize the missing batch dimension rather than blindly `squeeze()`-ing. |
| `LATENT` | Dictionary whose main tensor is commonly under `"samples"` with shape `[B, C, H, W]` | Preserve additional dictionary keys. Do not assume every model family uses one fixed channel count or spatial scale. |

See the official [images, masks, and latents guide](https://docs.comfy.org/custom-nodes/backend/images_and_masks) and [tensor guide](https://docs.comfy.org/custom-nodes/backend/tensors).

Robust mask normalization:

```python
if mask.ndim == 2:
    mask = mask.unsqueeze(0)
if mask.ndim != 3:
    raise ValueError(f"Expected MASK [B,H,W] or [H,W], got {tuple(mask.shape)}")
```

Avoid an unconstrained `tensor.squeeze()`: a batch size, height, width, or channel size of one could be removed unintentionally.

### 9.3 Audio

Current ComfyUI audio payloads are dictionaries containing:

- `waveform`: tensor shaped `[B, C, T]`;
- `sample_rate`: integer sample rate.

Validate sample rate and shape before DSP. Preserve batch/channel semantics rather than assuming mono, unbatched audio.

## 10. ComfyUI lists versus tensor batches

These are separate layers:

- A **ComfyUI list** means multiple scheduling values flowing through graph sockets.
- A **tensor batch** is one Python value whose tensor has batch dimension `B`.

An `IMAGE` tensor `[8, H, W, C]` is one normal node input containing a batch of eight images. It is not automatically eight ComfyUI scheduling-list items.

### 10.1 Default list mapping

Internally, normal node outputs are represented as lists of length one. If an upstream output is marked as a ComfyUI list, default execution maps the consumer function across elements.

When input lists have different lengths, the current execution model repeats the last item of shorter lists and invokes up to the longest length. Results are collected per output. The official [list processing guide](https://docs.comfy.org/custom-nodes/backend/lists) describes this behavior, and the current mapping implementation is in [`execution.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/execution.py#L241-L317).

### 10.2 Receiving a whole ComfyUI list

V1:

```python
INPUT_IS_LIST = True

def execute(self, values):
    # `values` is a list even when one widget value was supplied.
    ...
```

V3:

```python
return io.Schema(
    ...,
    is_input_list=True,
)
```

List mode applies to **all** inputs. Widget literals also arrive wrapped in a list. Do not enable it for one parameter and assume other parameters remain scalar.

### 10.3 Producing a scheduling list

V1:

```python
RETURN_TYPES = ("IMAGE", "INT")
OUTPUT_IS_LIST = (True, False)
```

V3:

```python
outputs=[
    io.Image.Output("images", is_output_list=True),
    io.Int.Output("count"),
]
```

For an output marked as a list, the returned Python list is propagated as multiple scheduling values rather than wrapped as one value. Keep list flags aligned exactly with outputs.

Tensor batch processing remains the node’s responsibility. If a node claims to support `IMAGE`, tests should cover `B > 1` even when no ComfyUI list flags are used.

## 11. Graph expansion and blockers

Node expansion lets a node return a subgraph for execution. It is appropriate when the work should remain expressible as ComfyUI nodes rather than being hidden inside a monolithic Python call.

Key points:

- Use ComfyUI’s `GraphBuilder` rather than manually inventing prompt structures.
- `rawLink` inputs let an expanding node receive upstream link descriptors without executing them first.
- V3 requires `Schema.enable_expand=True` before returning expansion data in `NodeOutput`.
- `DYNPROMPT` is the mutable graph context used during expansion.
- `ExecutionBlocker` can prevent a branch from executing or propagate an error/message.

Expansion changes scheduling, cache ancestry, and validation, so keep an ordinary single-node implementation unless expansion offers a concrete graph-level benefit. Start with the official [expansion documentation](https://docs.comfy.org/custom-nodes/backend/expansion).

## 12. Backend routes, assets, and frontend extensions

Most computational nodes need no custom route and no JavaScript. The node schema already reaches the frontend through `/object_info`.

### 12.1 Custom HTTP routes

When a custom client/server operation is necessary:

```python
from aiohttp import web
from server import PromptServer


@PromptServer.instance.routes.get("/lfgg/v1/status")
async def get_status(request):
    return web.json_response({"ok": True})
```

These decorators only register `aiohttp` handlers. The audited standalone
server does not place a general authentication or authorization gate around
custom routes, so assume that any client able to reach ComfyUI can call them
unless the deployment adds a trusted proxy or middleware. CORS is not an
authentication control. Never expose secrets or privileged operations by
default; add explicit authorization when a route genuinely needs them. This
is an inference from the current route-registration and middleware paths in
[`server.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/server.py#L115-L190)
and its
[`add_routes` implementation](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/server.py#L1218-L1230).
The `Comfy-User` header selects a local profile rather than authenticating an
identity, and Comfy account keys cover paid Partner Nodes rather than local
custom routes; see the current
[`UserManager`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/app/user_manager.py#L41-L55)
and [API-key scope](https://docs.comfy.org/development/comfyui-server/api-key-integration).

`PromptServer` exists before custom-node imports, and routes are attached after imports, so import-time route decorators work in the current startup sequence. See [`main.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/main.py#L488-L523) and the official [routes and communications guide](https://docs.comfy.org/development/comfyui-server/comms_routes).

Guidelines:

- Namespace paths, for example `/lfgg/v1/...`, to avoid collisions.
- Validate request bodies, query parameters, paths, and sizes.
- Apply authentication/authorization if the route exposes sensitive operations.
- Prevent path traversal; never concatenate an untrusted path into a filesystem target.
- Avoid unauthenticated arbitrary-file or arbitrary-URL fetch endpoints.
- Use the frontend API helper (`api.fetchApi`) rather than hard-coding server origins.
- Keep routes thin; graph computation belongs in nodes so it remains queueable, inspectable, and reproducible.

Current server routing publishes ordinary routes both without and with the `/api` prefix, as shown in [`server.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/server.py#L1218-L1230). Treat the documented frontend helper as the client contract instead of duplicating that routing behavior yourself.

### 12.2 Frontend assets

The documented package mechanism is:

```python
WEB_DIRECTORY = "./web"
```

ComfyUI serves the directory under `/extensions/<module-name>` and discovers JavaScript extensions. The official [JavaScript overview](https://docs.comfy.org/custom-nodes/js/javascript_overview) describes `WEB_DIRECTORY` and `app.registerExtension`. Current static serving is in [`server.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/server.py#L1232-L1234), and JS discovery is in [`server.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/server.py#L356-L368).

Only add a frontend extension for behavior the schema cannot express. Give the extension a globally unique name. Prefer documented extension hooks over monkey-patching frontend internals.

The current loader can also read a `[tool.comfy].web` path from `pyproject.toml` and automatically register it, visible in [`nodes.py`](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/nodes.py#L2251-L2268). This is **source-only** in the audited material and should not replace `WEB_DIRECTORY` as the compatibility baseline without an explicit tested-version requirement.

Copying JavaScript directly into ComfyUI’s own web directory is deprecated; package assets with the custom node.

## 13. Practical design rules for this repository

1. **Choose one registration generation first.** Use V1 unless a stated requirement needs V3-only behavior.
2. **Prefix all serialized IDs.** Use `LFGG_...` for node and custom socket IDs.
3. **Keep IDs stable.** Treat display names and categories as the cosmetic layer.
4. **Keep import time cheap.** No model loads, device allocations, or remote calls at module import.
5. **Make behavior graph-visible.** Seeds, modes, paths, and meaningful settings belong in declared inputs.
6. **Validate trust boundaries in the backend.** A frontend widget is not an enforcement boundary.
7. **Design for caching.** Deterministic nodes need no hook; external state needs an explicit input or fingerprint.
8. **Test batches and list semantics separately.** At minimum, test image batch `B=1` and `B>1`; test scheduling lists only for nodes that declare them.
9. **Preserve opaque payloads.** In particular, retain extra latent dictionary fields unless the node’s documented purpose replaces them.
10. **Avoid hidden/frontend/server APIs until required.** A plain backend node is easier to install, test, and maintain.

### Recommended test matrix

| Area | Minimum cases |
|---|---|
| Registration | Clean startup; all expected IDs visible in `/object_info`; no collision warning |
| Required/optional inputs | Optional omitted; optional supplied; malformed literal rejected |
| Outputs | Output count/type order matches schema |
| Caching | Same inputs reuse deterministic result; changed explicit input invalidates; external file change invalidates if supported |
| Images/masks | Image `B=1` and `B>1`; mask `[H,W]` and `[B,H,W]` |
| Lists | Scalar/default mapping; whole-list mode if declared; mismatched list lengths if accepted |
| Lazy | Each branch selected; unselected branch does not execute |
| Errors | User-actionable validation/execution messages; no sensitive values in logs |
| Compatibility | Minimum supported ComfyUI/frontend version and current version |

## 14. Deprecated, experimental, and avoid-list

| Surface | Status | Guidance |
|---|---|---|
| V1 class API | Legacy-supported | Safe compatibility baseline today; no formal removal schedule was found in the audited primary sources. |
| V3 `comfy_api.latest` | Current experimental | Use with a minimum version and migration budget. |
| V3 `v0_0_2` | Current experimental | It is also marked unstable and reuses latest schema exports; do not describe it as stable. |
| V3 `v0_0_1` | Template-only despite stable flag | Do not use. |
| `defaultInput` | Deprecated | Remove on required inputs; replace with `forceInput` on optional inputs when needed. |
| List-first combo declaration | Legacy-compatible/outdated | Prefer `("COMBO", {"options": [...]})` for current targets. |
| `"*"` / `IO.ANY` | Workaround with known limitations | Prefer concrete/custom types or carefully chosen V3 polymorphism. |
| `[tool.comfy].web` | Source-only in this audit | Prefer documented `WEB_DIRECTORY` for compatibility. |
| Frontend monkey-patching/hijacking | Deprecated/fragile pattern | Use documented extension hooks. |
| Copying assets into ComfyUI core web files | Deprecated | Ship a package-local web directory. |

## 15. Documentation/source discrepancies and unresolved risks

These are important enough to re-check when implementation begins:

1. **V3 stability conflict.** The migration guide’s stability language does not match the audited source flags. Both usable V3 imports are unstable in source.
2. **Lifecycle page is V1-centric.** It presents `NODE_CLASS_MAPPINGS` and `__all__`; the current loader also supports V3 and does not inspect `__all__`.
3. **The V3 schema table can lag source.** The current `Schema` includes fields not fully covered by the migration page. Treat newly observed fields as experimental unless documented.
4. **Combo guidance has evolved.** Some documentation/examples retain the list-first form, while current type/source comments call it outdated.
5. **Mask shape wording varies.** Follow the more specific images/masks guide and accept both canonical `[B,H,W]` and the common single-mask `[H,W]` case.
6. **V1 has no discovered formal stability/removal promise.** “Legacy-supported” describes current implementation, not an indefinite guarantee.
7. **Frontend metadata has version floors.** `socketless`, `widgetType`, and future options may render differently on older separately installed frontend packages.
8. **Model payload assumptions evolve.** Do not hard-code one latent channel count, spatial scale, model class implementation, or conditioning internals across all model families.
9. **Source-only behavior can change without migration guarantees.** This particularly applies to `[tool.comfy].web` and newly added V3 schema fields.

## 16. Primary-source index

Official guides:

- [Custom-node overview](https://docs.comfy.org/custom-nodes/overview)
- [Backend lifecycle](https://docs.comfy.org/custom-nodes/backend/lifecycle)
- [Server-side node overview](https://docs.comfy.org/custom-nodes/backend/server_overview)
- [Data types](https://docs.comfy.org/custom-nodes/backend/datatypes)
- [More on inputs and custom validation](https://docs.comfy.org/custom-nodes/backend/more_on_inputs)
- [List processing](https://docs.comfy.org/custom-nodes/backend/lists)
- [Lazy evaluation](https://docs.comfy.org/custom-nodes/backend/lazy_evaluation)
- [Node expansion](https://docs.comfy.org/custom-nodes/backend/expansion)
- [Images, masks, and latents](https://docs.comfy.org/custom-nodes/backend/images_and_masks)
- [Tensors](https://docs.comfy.org/custom-nodes/backend/tensors)
- [V3 migration](https://docs.comfy.org/custom-nodes/v3_migration)
- [JavaScript extensions](https://docs.comfy.org/custom-nodes/js/javascript_overview)
- [Server routes and communications](https://docs.comfy.org/development/comfyui-server/comms_routes)

Pinned implementation anchors:

- [Custom-node loader and registration precedence](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/nodes.py#L2227-L2371)
- [V1 typing and class contract](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy/comfy_types/node_typing.py#L16-L320)
- [V3 schema](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy_api/latest/_io.py#L1587-L1765)
- [V3 node and output contract](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy_api/latest/_io.py#L1859-L2245)
- [Execution, validation, lazy resolution, and fingerprints](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/execution.py)
- [Cache signatures](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/comfy_execution/caching.py#L82-L148)
- [Current official example node](https://github.com/Comfy-Org/ComfyUI/blob/806e092ed42772e4ce7abf44c97c50021cc4bd10/custom_nodes/example_node.py.example#L1-L130)
