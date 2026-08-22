import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[2] / "lfgg_nodes" / "string_replace.py"
SPEC = importlib.util.spec_from_file_location("lfgg_string_replace", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_schemas_are_exact_and_compact():
    assert MODULE.StringReplace.DESCRIPTION == (
        "Replaces every literal search match in text."
    )
    assert MODULE.StringReplace.FUNCTION == "replace"
    assert MODULE.StringReplace.RETURN_TYPES == ("STRING",)
    assert MODULE.StringReplace.RETURN_NAMES == ("text",)
    assert MODULE.StringReplace.OUTPUT_TOOLTIPS == ("Text after every replacement.",)
    assert MODULE.StringReplace.INPUT_TYPES() == {
        "required": {
            "text": (
                "STRING",
                {
                    "default": "",
                    "multiline": True,
                    "tooltip": "Text to transform.",
                },
            ),
            "search": (
                "STRING",
                {"default": "", "tooltip": "Literal text to find."},
            ),
            "replacement": (
                "STRING",
                {"default": "", "tooltip": "Literal text to insert."},
            ),
            "case_sensitive": (
                "BOOLEAN",
                {
                    "default": True,
                    "label_on": "Match case",
                    "label_off": "Ignore case",
                    "tooltip": "Match case; disable for case-insensitive matching.",
                },
            ),
        }
    }
    assert MODULE.StringReplaceRegex.DESCRIPTION == (
        "Replaces every literal or regular-expression search match in text."
    )
    assert MODULE.StringReplaceRegex.FUNCTION == "replace"
    assert MODULE.StringReplaceRegex.RETURN_TYPES == ("STRING",)
    assert MODULE.StringReplaceRegex.RETURN_NAMES == ("text",)
    assert MODULE.StringReplaceRegex.OUTPUT_TOOLTIPS == (
        "Text after every replacement.",
    )
    assert MODULE.StringReplaceRegex.INPUT_TYPES() == {
        "required": {
            "text": (
                "STRING",
                {
                    "default": "",
                    "multiline": True,
                    "tooltip": "Text to transform.",
                },
            ),
            "search": (
                "STRING",
                {"default": "", "tooltip": "Text or regex to find."},
            ),
            "replacement": (
                "STRING",
                {"default": "", "tooltip": "Text or regex replacement."},
            ),
            "use_regex": (
                "BOOLEAN",
                {
                    "default": True,
                    "label_on": "Use regex",
                    "label_off": "Literal text",
                    "tooltip": (
                        "Use regex; disable for literal search and replacement."
                    ),
                },
            ),
            "case_sensitive": (
                "BOOLEAN",
                {
                    "default": True,
                    "label_on": "Match case",
                    "label_off": "Ignore case",
                    "tooltip": "Match case; disable for case-insensitive matching.",
                },
            ),
        }
    }


def test_literal_replacement_respects_case_only_for_matching():
    node = MODULE.StringReplace()

    assert node.replace("CAT Cat cat", "cat", "dog", False) == ("dog dog dog",)
    assert node.replace("KkK", "k", "x", False) == ("xxx",)
    assert node.replace("a.b a.b", ".", r"\n", True) == (r"a\nb a\nb",)
    assert node.replace("remove me", "remove me", "", True) == ("",)
    assert MODULE.StringReplaceRegex().replace("a.b", ".", r"\1", False, True) == (
        r"a\1b",
    )


def test_empty_search_passes_text_through():
    assert MODULE.StringReplace().replace("unchanged", "", "ignored") == (
        "unchanged",
    )
    assert MODULE.StringReplaceRegex().replace("unchanged", "", r"\1") == (
        "unchanged",
    )
    assert MODULE.StringReplace().replace("", "", "ignored") == ("",)


def test_regex_supports_inline_flags_capture_references_and_zero_width_matches():
    node = MODULE.StringReplaceRegex()

    assert node.replace("A-12 b-34", r"(?i)([a-z])-(\d+)", r"\2/\1") == (
        "12/A 34/b",
    )
    assert node.replace("aba", r"(?=a)", "X") == ("XabXa",)
    assert node.replace("x", "(x)", r"\123") == ("S",)
    assert node.replace("b", r"(?P<optional>a)?b", r"[\g<optional>]") == ("[]",)


@pytest.mark.parametrize(
    ("node", "kwargs", "message"),
    [
        (
            MODULE.StringReplaceRegex(),
            {"text": "x", "search": "(", "replacement": "", "use_regex": True},
            "invalid regex search",
        ),
        (
            MODULE.StringReplaceRegex(),
            {"text": "no match", "search": "(x)", "replacement": r"\2"},
            "invalid regex replacement",
        ),
        (
            MODULE.StringReplace(),
            {"text": 1, "search": "x", "replacement": ""},
            "text must be a string",
        ),
        (
            MODULE.StringReplace(),
            {"text": "x", "search": 1, "replacement": ""},
            "search must be a string",
        ),
        (
            MODULE.StringReplace(),
            {"text": "x", "search": "x", "replacement": 1},
            "replacement must be a string",
        ),
        (
            MODULE.StringReplace(),
            {"text": "x", "search": "x", "replacement": "", "case_sensitive": 1},
            "case_sensitive must be Boolean",
        ),
        (
            MODULE.StringReplaceRegex(),
            {
                "text": "x",
                "search": "x",
                "replacement": "",
                "use_regex": "yes",
            },
            "use_regex must be Boolean",
        ),
    ],
)
def test_rejects_invalid_inputs(node, kwargs, message):
    with pytest.raises(MODULE.StringReplaceError, match=message):
        node.replace(**kwargs)


def test_enforces_utf8_byte_limits_and_output_bound(monkeypatch):
    node = MODULE.StringReplace()
    monkeypatch.setattr(MODULE, "TEXT_LIMIT", 3)
    with pytest.raises(MODULE.StringReplaceError, match="text exceeds"):
        node.replace("éé", "é", "x")

    monkeypatch.setattr(MODULE, "TEXT_LIMIT", 1024)
    monkeypatch.setattr(MODULE, "OUTPUT_LIMIT", 4)
    with pytest.raises(MODULE.StringReplaceError, match="replaced text exceeds"):
        node.replace("aa", "a", "éé")

    monkeypatch.setattr(MODULE, "SEARCH_LIMIT", 3)
    with pytest.raises(MODULE.StringReplaceError, match="search exceeds"):
        node.replace("x", "éé", "")

    monkeypatch.setattr(MODULE, "SEARCH_LIMIT", 1024)
    monkeypatch.setattr(MODULE, "TEXT_LIMIT", 3)
    with pytest.raises(MODULE.StringReplaceError, match="replacement exceeds"):
        node.replace("x", "x", "éé")


def test_bounds_regex_capture_expansion_before_expanding(monkeypatch):
    monkeypatch.setattr(MODULE, "OUTPUT_LIMIT", 5)

    with pytest.raises(MODULE.StringReplaceError, match="replaced text exceeds"):
        MODULE.StringReplaceRegex().replace("abcd", "(.*)", r"\1\1")


def test_allows_capture_expansion_that_fits_the_output_limit(monkeypatch):
    monkeypatch.setattr(MODULE, "OUTPUT_LIMIT", 4)

    assert MODULE.StringReplaceRegex().replace("abcd", "(abcd)", r"\1") == ("abcd",)

    monkeypatch.setattr(MODULE, "OUTPUT_LIMIT", 1)
    assert MODULE.StringReplaceRegex().replace("x" * 99, "(x)" * 99, r"\99") == (
        "x",
    )

    match = MODULE.re.fullmatch("()" * 98 + "(.*)", "abcd")
    assert MODULE._replacement_bound(match, r"\999") == 5


@pytest.mark.parametrize(
    "search",
    [
        "(" * 600 + "x" + ")" * 600,
        "x{999999999999999999999999999999999999999999999999999999999999999}",
    ],
)
def test_wraps_extreme_regex_compiler_errors(search):
    with pytest.raises(MODULE.StringReplaceError, match="invalid regex search"):
        MODULE.StringReplaceRegex().replace("x", search, "")
