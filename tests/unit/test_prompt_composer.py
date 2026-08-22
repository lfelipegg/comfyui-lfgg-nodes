import asyncio
import importlib.util
import json
import random
import sys
import threading
from types import SimpleNamespace

import pytest

import lfgg_nodes.prompt_composer as prompt_composer
from lfgg_nodes.prompt_composer import (
    PromptComposer,
    PromptComposerError,
    library_catalog,
    prompt_composer_libraries,
)


def configured_library(monkeypatch, tmp_path, *, styles=None):
    user = tmp_path / "user"
    wildcards = tmp_path / "wildcards"
    styles_path = tmp_path / "styles.csv"
    (user / "lfgg_nodes").mkdir(parents=True)
    wildcards.mkdir()
    styles_path.write_text(
        styles
        or (
            "name,prompt,negative_prompt\n"
            "--- Styles ---,,\n"
            'Cinematic,"cinematic, vivid"," low quality, blurry, "\n'
            'Negative only,,"oversaturated,"\n'
        ),
        encoding="utf-8",
    )
    config = {
        "prompt_composer": {
            "styles_csv": str(styles_path.resolve()),
            "wildcards": str(wildcards.resolve()),
        }
    }
    (user / "lfgg_nodes" / "config.json").write_text(
        json.dumps(config), encoding="utf-8"
    )
    monkeypatch.setitem(
        sys.modules,
        "folder_paths",
        SimpleNamespace(get_user_directory=lambda: str(user)),
    )
    return user, styles_path, wildcards


def test_schema_is_file_free_and_exact():
    assert PromptComposer.CATEGORY == "LFGG/text"
    assert PromptComposer.FUNCTION == "compose"
    assert PromptComposer.RETURN_TYPES == ("STRING", "STRING")
    assert PromptComposer.RETURN_NAMES == ("prompt", "negative_prompt")
    assert PromptComposer.INPUT_TYPES() == {
        "required": {
            "prompt_template": (
                "STRING",
                {
                    "default": "",
                    "multiline": True,
                    "dynamicPrompts": True,
                    "placeholder": "Write a prompt and insert styles or wildcards…",
                    "tooltip": (
                        "Prompt template. File wildcards use __folder/name__; "
                        "styles use [[style:Exact Name]]."
                    ),
                },
            ),
            "seed": (
                "INT",
                {
                    "default": 0,
                    "min": 0,
                    "max": 2**64 - 1,
                    "control_after_generate": True,
                    "tooltip": "Seed for reproducible file-wildcard choices.",
                },
            ),
        }
    }


def test_catalog_preserves_styles_and_sorts_wildcards_with_disabled_entries(
    monkeypatch, tmp_path
):
    _, _, wildcards = configured_library(monkeypatch, tmp_path)
    (wildcards / "Zoo.TXT").write_text(" zebra \n\n#literal\n", encoding="utf-8")
    (wildcards / "empty.txt").write_text("\n  \n", encoding="utf-8")
    nested = wildcards / "sub"
    nested.mkdir()
    (nested / "animals.txt").write_text("cat\ndog\n", encoding="utf-8")

    catalog = library_catalog()

    assert catalog == {
        "styles": [
            {"name": "--- Styles ---", "disabled": True},
            {"name": "Cinematic", "disabled": False},
            {"name": "Negative only", "disabled": False},
        ],
        "wildcards": [
            {"name": "empty", "disabled": True},
            {"name": "sub/animals", "disabled": False},
            {"name": "Zoo", "disabled": False},
        ],
    }
    assert str(tmp_path) not in json.dumps(catalog)


def test_composes_positioned_tokens_reproducibly_and_leaves_nested_fragments_literal(
    monkeypatch, tmp_path
):
    _, _, wildcards = configured_library(monkeypatch, tmp_path)
    nested = wildcards / "sub"
    nested.mkdir()
    (nested / "animals.txt").write_text("cat\ndog\ncat\n", encoding="utf-8")
    (wildcards / "nested.txt").write_text("__missing__\n", encoding="utf-8")
    template = (
        "A __sub/animals__, [[style:Cinematic]], __sub/animals__, "
        "[[style:Negative only]], \\__literal__, "
        "\\[[style:Cinematic]], __nested__, {red|blue}"
    )

    first = PromptComposer().compose(template, 42)
    second = PromptComposer().compose(template, 42)
    draws = random.Random(42)
    expected = [draws.choice(["cat", "dog", "cat"]) for _ in range(2)]

    assert first == second
    assert first[0] == (
        f"A {expected[0]}, cinematic, vivid, {expected[1]}, , "
        "__literal__, [[style:Cinematic]], __missing__, {red|blue}"
    )
    assert first[1] == "low quality, blurry, oversaturated"


@pytest.mark.parametrize(
    ("template", "message"),
    [
        ("[[style:--- Styles ---]]", "is a heading"),
        ("[[style:Removed]]", "is unavailable"),
        ("__empty__", "is empty"),
        ("__SUB/animals__", "is unavailable"),
        ("__../outside__", "invalid wildcard token"),
    ],
)
def test_rejects_disabled_missing_and_unsafe_references(
    monkeypatch, tmp_path, template, message
):
    _, _, wildcards = configured_library(monkeypatch, tmp_path)
    (wildcards / "empty.txt").write_text("\n", encoding="utf-8")
    sub = wildcards / "sub"
    sub.mkdir()
    (sub / "animals.txt").write_text("cat\n", encoding="utf-8")

    with pytest.raises(PromptComposerError, match=message):
        PromptComposer().compose(template, 0)


def test_rejects_strict_config_and_symlink_escape_without_disclosing_paths(
    monkeypatch, tmp_path
):
    user, _, wildcards = configured_library(monkeypatch, tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("private\n", encoding="utf-8")
    try:
        (wildcards / "escape.txt").symlink_to(outside)
    except (NotImplementedError, OSError):
        pytest.skip("symlinks are unavailable")

    with pytest.raises(PromptComposerError) as caught:
        library_catalog()
    assert "escapes the wildcard root" in str(caught.value)
    assert str(tmp_path) not in str(caught.value)

    config_path = user / "lfgg_nodes" / "config.json"
    config = json.loads(config_path.read_text())
    config["unexpected"] = True
    config_path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(PromptComposerError, match="only the prompt_composer"):
        library_catalog()


def test_enforces_wildcard_size_and_csv_uniqueness(monkeypatch, tmp_path):
    _, styles, wildcards = configured_library(monkeypatch, tmp_path)
    (wildcards / "large.txt").write_text("1234", encoding="utf-8")
    monkeypatch.setattr(prompt_composer, "WILDCARD_LIMIT", 3)
    with pytest.raises(PromptComposerError, match="size limit"):
        library_catalog()

    styles.write_text(
        "name,prompt,negative_prompt\nSame,a,\nSame,b,\n", encoding="utf-8"
    )
    with pytest.raises(PromptComposerError, match="repeats style"):
        library_catalog()


def test_rejects_unterminated_and_oversized_csv_fields(monkeypatch, tmp_path):
    _, styles, _ = configured_library(monkeypatch, tmp_path)
    styles.write_text(
        'name,prompt,negative_prompt\nBroken,"unterminated\n', encoding="utf-8"
    )
    with pytest.raises(PromptComposerError, match="malformed"):
        library_catalog()

    styles.write_text(
        "name,prompt,negative_prompt\n"
        f"Exact,{'x' * prompt_composer.CSV_FIELD_LIMIT},\n",
        encoding="utf-8",
    )
    assert library_catalog()["styles"][0]["name"] == "Exact"
    styles.write_text(
        "name,prompt,negative_prompt\n"
        f"Too large,{'x' * (prompt_composer.CSV_FIELD_LIMIT + 1)},\n",
        encoding="utf-8",
    )
    with pytest.raises(PromptComposerError, match="field exceeds the 128 KiB limit"):
        library_catalog()


def test_catalog_limits_every_visited_entry(monkeypatch, tmp_path):
    _, _, wildcards = configured_library(monkeypatch, tmp_path)
    (wildcards / "directory").mkdir()
    (wildcards / "ignored.bin").write_text("ignored", encoding="utf-8")
    (wildcards / "choice.txt").write_text("choice", encoding="utf-8")
    monkeypatch.setattr(prompt_composer, "WILDCARD_COUNT_LIMIT", 2)

    with pytest.raises(PromptComposerError, match="entry limit"):
        library_catalog()


def test_bounds_resolved_output_before_building_it(monkeypatch, tmp_path):
    configured_library(
        monkeypatch,
        tmp_path,
        styles=(
            "name,prompt,negative_prompt\n"
            "Wide,123456789012345678901,\n"
        ),
    )
    monkeypatch.setattr(prompt_composer, "OUTPUT_LIMIT", 20)

    with pytest.raises(PromptComposerError, match="resolved prompt"):
        PromptComposer().compose("[[style:Wide]]", 0)


def test_fingerprint_tracks_referenced_external_content(monkeypatch, tmp_path):
    _, styles, wildcards = configured_library(monkeypatch, tmp_path)
    source = wildcards / "choice.txt"
    source.write_text("one\n", encoding="utf-8")
    template = "__choice__ [[style:Cinematic]]"

    first = PromptComposer.IS_CHANGED(template, 1)
    source.write_text("two\n", encoding="utf-8")
    second = PromptComposer.IS_CHANGED(template, 1)
    styles.write_text(
        "name,prompt,negative_prompt\nCinematic,changed,bad\n", encoding="utf-8"
    )
    third = PromptComposer.IS_CHANGED(template, 1)

    assert len({first, second, third}) == 3
    assert PromptComposer.IS_CHANGED("__missing__", 1).startswith("error:")


def test_refresh_route_returns_bounded_safe_validation_error(monkeypatch, tmp_path):
    user, _, _ = configured_library(monkeypatch, tmp_path)
    (user / "lfgg_nodes" / "config.json").write_text("{}", encoding="utf-8")
    responses = []

    def json_response(payload, status=200):
        responses.append((payload, status))
        return payload, status

    monkeypatch.setitem(
        sys.modules,
        "aiohttp",
        SimpleNamespace(web=SimpleNamespace(json_response=json_response)),
    )

    asyncio.run(prompt_composer_libraries(None))

    assert responses == [
        (
            {
                "ok": False,
                "error": "configuration must contain only the prompt_composer section",
            },
            400,
        )
    ]
    assert str(tmp_path) not in json.dumps(responses)


def test_refresh_route_scans_libraries_off_the_event_loop(monkeypatch):
    responses = []

    def catalog():
        assert threading.current_thread() is not threading.main_thread()
        return {"styles": [], "wildcards": []}

    monkeypatch.setattr(prompt_composer, "library_catalog", catalog)
    monkeypatch.setitem(
        sys.modules,
        "aiohttp",
        SimpleNamespace(
            web=SimpleNamespace(
                json_response=lambda payload, status=200: responses.append(
                    (payload, status)
                )
                or (payload, status)
            )
        ),
    )

    asyncio.run(prompt_composer_libraries(None))

    assert responses == [({"ok": True, "styles": [], "wildcards": []}, 200)]


def test_refresh_route_coalesces_concurrent_scans(monkeypatch):
    responses = []

    monkeypatch.setitem(
        sys.modules,
        "aiohttp",
        SimpleNamespace(
            web=SimpleNamespace(
                json_response=lambda payload, status=200: responses.append(
                    (payload, status)
                )
                or (payload, status)
            )
        ),
    )

    async def check():
        gate = asyncio.Event()
        calls = 0

        async def to_thread(function):
            nonlocal calls
            assert function is prompt_composer.library_catalog
            calls += 1
            await gate.wait()
            return {"styles": [], "wildcards": []}

        monkeypatch.setattr(prompt_composer.asyncio, "to_thread", to_thread)
        first = asyncio.create_task(prompt_composer_libraries(None))
        await asyncio.sleep(0)
        second = asyncio.create_task(prompt_composer_libraries(None))
        await asyncio.sleep(0)
        assert calls == 1
        gate.set()
        await asyncio.gather(first, second)
        await prompt_composer_libraries(None)
        assert calls == 2

    asyncio.run(check())
    assert len(responses) == 3


def test_registers_the_read_only_refresh_route(monkeypatch):
    registered = []

    class Routes:
        @staticmethod
        def get(path):
            def register(handler):
                registered.append((path, handler))
                return handler

            return register

    monkeypatch.setitem(
        sys.modules,
        "server",
        SimpleNamespace(PromptServer=SimpleNamespace(instance=SimpleNamespace(routes=Routes()))),
    )
    spec = importlib.util.spec_from_file_location(
        "lfgg_prompt_composer_route_test", prompt_composer.__file__
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert len(registered) == 1
    assert registered[0][0] == "/lfgg/v1/prompt-composer/libraries"
    assert asyncio.iscoroutinefunction(registered[0][1])
