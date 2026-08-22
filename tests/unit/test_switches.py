import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[2] / "lfgg_nodes" / "switches.py"
SPEC = importlib.util.spec_from_file_location("lfgg_switches", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_boolean_switch_selects_only_the_requested_branch():
    node = MODULE.BooleanSwitch()

    assert node.check_lazy_status(condition=False, false=None, true=None) == ["false"]
    assert node.check_lazy_status(condition=True, false=None, true=None) == ["true"]
    assert node.select(condition=False, false="off") == ("off",)
    assert node.select(condition=True, true="on") == ("on",)


def test_index_switch_schema_is_bounded_and_lazy():
    optional = MODULE.IndexSwitch.INPUT_TYPES()["optional"]

    assert list(optional) == [f"branch_{index}" for index in range(32)]
    assert all(
        config == ("*", {"forceInput": True, "lazy": True})
        for config in optional.values()
    )
    assert MODULE.IndexSwitch().check_lazy_status(
        index=2, branch_2=None
    ) == ["branch_2"]
    assert MODULE.IndexSwitch().select(index=2, branch_2="third") == ("third",)
    assert MODULE.IndexSwitch().select(index=2, branch_2=None) == (None,)


@pytest.mark.parametrize(
    ("node", "kwargs", "message"),
    [
        (MODULE.BooleanSwitch(), {"condition": 1}, "condition must be Boolean"),
        (MODULE.IndexSwitch(), {"index": True}, "index must be an integer"),
        (MODULE.IndexSwitch(), {"index": -1}, "between 0 and 31"),
        (MODULE.IndexSwitch(), {"index": 32}, "between 0 and 31"),
        (MODULE.BooleanSwitch(), {"condition": False}, "selected branch 'false'"),
        (
            MODULE.BooleanSwitch(),
            {"condition": False, "false": 0, "other": 1},
            "unsupported branch 'other'",
        ),
    ],
)
def test_switches_reject_invalid_selectors_and_missing_selected_branches(
    node, kwargs, message
):
    with pytest.raises(ValueError, match=message):
        node.select(**kwargs)


def test_wildcard_prompt_validation_still_leaves_runtime_validation_in_place():
    assert MODULE.BooleanSwitch.VALIDATE_INPUTS({"false": "IMAGE"}) is True
    with pytest.raises(ValueError, match="condition must be Boolean"):
        MODULE.BooleanSwitch().check_lazy_status(condition="false", false=None)
