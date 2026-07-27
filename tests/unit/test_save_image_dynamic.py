from datetime import datetime

import pytest

from lfgg_nodes.save_image_dynamic import (
    ParsedTemplate,
    render_filename,
    render_relative_path,
)

NOW = datetime(2026, 7, 27, 15, 4, 5)


def render(template, **overrides):
    values = {
        "model": None,
        "timestamp": NOW,
        "width": 64,
        "height": 32,
        "batch": 0,
        "counter": 1,
    }
    values.update(overrides)
    return template.render(**values)


def test_template_expands_supported_tokens_and_defaults():
    template = ParsedTemplate(
        "{model}|{date}|{time}|{datetime}|{width}|{height}|{batch}|{counter}",
        input_name="filename_template",
    )

    assert render(template) == (
        "unknown_model|2026-07-27|15-04-05|2026-07-27_15-04-05|"
        "64|32|0|00001"
    )
    assert render(template, model="  ") == render(template)


def test_template_allows_literal_braces_and_reuses_the_supplied_timestamp():
    template = ParsedTemplate(
        "{{run}}_{date}_{time}",
        input_name="filename_template",
    )

    assert render(template) == "{run}_2026-07-27_15-04-05"
    assert render(template, batch=9) == "{run}_2026-07-27_15-04-05"


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("{missing}", "unknown field"),
        ("{model!r}", "conversions"),
        ("{counter:03}", "format specifications"),
        ("{model.value}", "unknown field"),
        ("{}", "unknown field"),
        ("{model", "malformed"),
    ],
)
def test_template_rejects_unsupported_or_malformed_fields(source, message):
    with pytest.raises(ValueError, match=message):
        ParsedTemplate(source, input_name="filename_template")


def test_template_enforces_input_and_counter_bounds():
    with pytest.raises(ValueError, match="512"):
        ParsedTemplate("x" * 513, input_name="path_template")

    template = ParsedTemplate("{counter}", input_name="filename_template")
    with pytest.raises(ValueError, match="counter"):
        render(template, counter=0)
    with pytest.raises(ValueError, match="counter"):
        render(template, counter=100_000)


def test_relative_path_sanitizes_components_and_protects_reserved_names():
    template = ParsedTemplate(
        r"runs\{model}\CON\a<b",
        input_name="path_template",
    )

    assert (
        render_relative_path(
            template,
            model="model/name",
            timestamp=NOW,
            width=64,
            height=32,
            batch=0,
            counter=1,
        ).as_posix()
        == "runs/model_name/_CON/a_b"
    )


@pytest.mark.parametrize(
    "source",
    ["/absolute", r"C:\drive", "../escape", r"nested\..\escape"],
)
def test_relative_path_rejects_absolute_drive_and_traversal(source):
    template = ParsedTemplate(source, input_name="path_template")

    with pytest.raises(ValueError, match="path_template"):
        render_relative_path(
            template,
            model="model",
            timestamp=NOW,
            width=64,
            height=32,
            batch=0,
            counter=1,
        )


def test_relative_path_allows_an_empty_subfolder():
    template = ParsedTemplate("", input_name="path_template")

    assert render_relative_path(
        template,
        model=None,
        timestamp=NOW,
        width=64,
        height=32,
        batch=0,
        counter=1,
    ).as_posix() == "."


def test_filename_normalizes_png_once_and_appends_a_counter_when_absent():
    plain = ParsedTemplate("image.png", input_name="filename_template")
    explicit = ParsedTemplate(
        "{model}_{counter}.png",
        input_name="filename_template",
    )

    assert render_filename(
        plain,
        counter_in_templates=False,
        model="model",
        timestamp=NOW,
        width=64,
        height=32,
        batch=0,
        counter=1,
    ) == "image_00001_.png"
    assert render_filename(
        explicit,
        counter_in_templates=True,
        model="a/b",
        timestamp=NOW,
        width=64,
        height=32,
        batch=0,
        counter=7,
    ) == "a_b_00007.png"


@pytest.mark.parametrize("source", ["CON", "nul.png", "LPT9"])
def test_filename_protects_windows_reserved_names(source):
    template = ParsedTemplate(source, input_name="filename_template")

    assert render_filename(
        template,
        counter_in_templates=True,
        model="model",
        timestamp=NOW,
        width=64,
        height=32,
        batch=0,
        counter=1,
    ).startswith("_")


@pytest.mark.parametrize("source", ["", ".png", "   ", "   .png"])
def test_filename_rejects_an_empty_stem(source):
    template = ParsedTemplate(source, input_name="filename_template")

    with pytest.raises(ValueError, match="filename_template"):
        render_filename(
            template,
            counter_in_templates=True,
            model="model",
            timestamp=NOW,
            width=64,
            height=32,
            batch=0,
            counter=1,
        )


def test_rendered_components_and_filename_stems_are_bounded():
    path = ParsedTemplate("x" * 201, input_name="path_template")
    filename = ParsedTemplate("x" * 201, input_name="filename_template")
    arguments = {
        "model": "model",
        "timestamp": NOW,
        "width": 64,
        "height": 32,
        "batch": 0,
        "counter": 1,
    }

    with pytest.raises(ValueError, match="200"):
        render_relative_path(path, **arguments)
    with pytest.raises(ValueError, match="200"):
        render_filename(filename, counter_in_templates=True, **arguments)
