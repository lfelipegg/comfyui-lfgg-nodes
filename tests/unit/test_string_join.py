import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[2] / "lfgg_nodes" / "string_join.py"
SPEC = importlib.util.spec_from_file_location("lfgg_string_join", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_schema_and_ordered_join_are_exact():
    node = MODULE.StringJoin()

    assert node.DESCRIPTION == (
        "Joins supplied text inputs in order with a literal separator."
    )
    assert node.FUNCTION == "join"
    assert node.RETURN_TYPES == ("STRING",)
    assert node.RETURN_NAMES == ("text",)
    assert node.OUTPUT_TOOLTIPS == ("Joined text.",)
    schema = node.INPUT_TYPES()
    assert schema["required"] == {
        "separator": (
            "STRING",
            {
                "default": "",
                "multiline": False,
                "tooltip": "Literal text placed between supplied inputs.",
            },
        )
    }
    assert list(schema["optional"]) == [f"text_{index}" for index in range(1, 33)]
    assert all(
        value == ("STRING", {"forceInput": True, "tooltip": "Ordered text input."})
        for value in schema["optional"].values()
    )
    assert node.join("|") == ("",)
    assert node.join("|", text_2="b", text_1="a", text_3="") == ("a|b|",)
    assert node.join("|", text_32="last") == ("last",)


@pytest.mark.parametrize(
    ("separator", "kwargs", "message"),
    [
        (1, {}, "separator must be a string"),
        ("", {"text_1": 1}, "text_1 must be a string"),
        ("", {"text_33": "x"}, "unsupported input"),
    ],
)
def test_rejects_invalid_inputs(separator, kwargs, message):
    with pytest.raises(MODULE.StringJoinError, match=message):
        MODULE.StringJoin().join(separator, **kwargs)


def test_enforces_utf8_input_and_precomputed_output_limits(monkeypatch):
    node = MODULE.StringJoin()
    monkeypatch.setattr(MODULE, "TEXT_LIMIT", 3)

    with pytest.raises(MODULE.StringJoinError, match="text_1 exceeds"):
        node.join("", text_1="éé")
    with pytest.raises(MODULE.StringJoinError, match="separator exceeds"):
        node.join("éé")
    with pytest.raises(MODULE.StringJoinError, match="joined text exceeds"):
        node.join("é", text_1="a", text_2="b")
    with pytest.raises(MODULE.StringJoinError, match="valid UTF-8"):
        node.join("", text_1="\ud800")
