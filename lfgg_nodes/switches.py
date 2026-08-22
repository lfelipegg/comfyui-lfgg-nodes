MAX_INDEX_BRANCHES = 32


def _boolean(value):
    if type(value) is not bool:
        raise ValueError("LFGG Boolean Switch condition must be Boolean")
    return value


def _index(value):
    if type(value) is not int:
        raise ValueError("LFGG Index Switch index must be an integer")
    if not 0 <= value < MAX_INDEX_BRANCHES:
        raise ValueError(
            f"LFGG Index Switch index must be between 0 and {MAX_INDEX_BRANCHES - 1}"
        )
    return value


def _branch(kwargs, name, node_name):
    if name not in kwargs:
        raise ValueError(f"LFGG {node_name} selected branch '{name}' is not connected")
    return kwargs[name]


class _Switch:
    CATEGORY = "LFGG/workflow"
    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("value",)
    OUTPUT_TOOLTIPS = ("Selected branch value.",)
    FUNCTION = "select"

    @classmethod
    def VALIDATE_INPUTS(cls, input_types):
        # ComfyUI's V1 wildcard requires opting out of its type comparison.
        return True

    def check_lazy_status(self, **kwargs):
        name = self._selected_name(**kwargs)
        return [name] if name in kwargs and kwargs[name] is None else []

    def select(self, **kwargs):
        unsupported = set(kwargs).difference({self._selector_name}, self._branch_names)
        if unsupported:
            raise ValueError(
                f"LFGG {self._node_name} received unsupported branch "
                f"'{sorted(unsupported)[0]}'"
            )
        return (_branch(kwargs, self._selected_name(**kwargs), self._node_name),)


class BooleanSwitch(_Switch):
    DESCRIPTION = "Selects the false or true branch without evaluating the other."
    _node_name = "Boolean Switch"
    _selector_name = "condition"
    _branch_names = frozenset(("false", "true"))

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "condition": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "False selects false; true selects true.",
                    },
                )
            },
            "optional": {
                "false": ("*", {"forceInput": True, "lazy": True}),
                "true": ("*", {"forceInput": True, "lazy": True}),
            },
        }

    def _selected_name(self, **kwargs):
        return "true" if _boolean(kwargs.get("condition")) else "false"


class IndexSwitch(_Switch):
    DESCRIPTION = "Selects one zero-based branch without evaluating the others."
    _node_name = "Index Switch"
    _selector_name = "index"
    _branch_names = frozenset(f"branch_{index}" for index in range(MAX_INDEX_BRANCHES))

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "index": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": MAX_INDEX_BRANCHES - 1,
                        "tooltip": "Zero-based branch index.",
                    },
                )
            },
            "optional": {
                f"branch_{index}": ("*", {"forceInput": True, "lazy": True})
                for index in range(MAX_INDEX_BRANCHES)
            },
        }

    def _selected_name(self, **kwargs):
        return f"branch_{_index(kwargs.get('index'))}"
