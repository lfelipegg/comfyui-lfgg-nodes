import pytest

import lfgg_nodes.prompt_assistant as prompt_assistant
from lfgg_nodes.prompt_assistant import (
    PromptAssistantError,
    build_system_message,
    discover_skills,
    parse_selection,
    read_attachments,
    resolve_selection,
    skill_files,
    strip_frontmatter,
)

SKILL_MD = "---\nname: {name}\ndescription: x\n---\n\n# {name}\n\nBody of {name}.\n"


def make_skill(root, name, references=(), extra=()):
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(SKILL_MD.format(name=name), encoding="utf-8")
    for relative in references:
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"Reference {relative}\n", encoding="utf-8")
    for relative in extra:
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not attachable\n", encoding="utf-8")
    return directory


def symlink(link, target):
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except (NotImplementedError, OSError):
        pytest.skip("symlinks are unavailable")


@pytest.fixture
def roots(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    make_skill(
        first,
        "scenario-maker-sdxl",
        references=(
            "references/models/sdxl.md",
            "references/routing.md",
            "CONTEXT.md",
        ),
        extra=(
            "evals/snapshot-1/SKILL.md",
            "docs/danbooru_tags/danbooru_tags.csv",
            "tests/test_skill.md",
            "scripts/tool.md",
            "wildcards/w.md",
            ".hidden/secret.md",
            "references/data.csv",
        ),
    )
    make_skill(first, "scenario-maker-wan")
    make_skill(first, "not-allowlisted")
    (first / "no-skill-file").mkdir()
    (first / "stray.md").write_text("x", encoding="utf-8")
    make_skill(second, "scenario-maker-sdxl", references=("references/other.md",))
    make_skill(second, "scenario-maker-pony")
    return first, second


def test_discovery_applies_allowlist_duplicates_and_missing_roots(roots, tmp_path):
    first, second = roots
    allowlist = (
        "scenario-maker-sdxl",
        "scenario-maker-pony",
        "scenario-maker-wan",
        "absent",
    )
    discovery = discover_skills(
        [str(first), str(second), str(tmp_path / "missing"), str(first / "stray.md")],
        allowlist,
    )

    assert sorted(discovery.skills) == [
        "scenario-maker-pony",
        "scenario-maker-sdxl",
        "scenario-maker-wan",
    ]
    assert discovery.skills["scenario-maker-sdxl"].root == str(first)
    assert discovery.skills["scenario-maker-sdxl"].path == (
        first / "scenario-maker-sdxl"
    ).resolve()
    assert discovery.skills["scenario-maker-pony"].root == str(second)
    assert discovery.missing == ("absent",)
    assert [root.available for root in discovery.roots] == [True, True, False, False]
    assert any("found in both" in warning for warning in discovery.warnings)
    assert any("missing" in warning for warning in discovery.warnings)
    assert "(missing)" in discovery.roots_searched()

    everything = discover_skills([str(first)], None)
    assert "not-allowlisted" in everything.skills
    assert everything.missing == ()
    assert "no-skill-file" not in everything.skills


def test_discovery_follows_symlinked_skills_inside_the_root_only(roots, tmp_path):
    first, _ = roots
    outside = tmp_path / "outside"
    make_skill(outside, "escaped")
    symlink(first / "escaped", outside / "escaped")
    inner = first / "_targets" / "linked"
    inner.mkdir(parents=True)
    (inner / "SKILL.md").write_text("linked body\n", encoding="utf-8")
    symlink(first / "linked", inner)

    discovery = discover_skills([str(first)], None)

    assert "escaped" not in discovery.skills
    assert "linked" in discovery.skills
    assert discovery.skills["linked"].path == inner.resolve()
    assert any("escapes its root" in warning for warning in discovery.warnings)


def test_skill_files_exclude_snapshots_hidden_and_non_markdown(roots):
    first, _ = roots
    discovery = discover_skills([str(first)], None)
    files = skill_files(discovery.skills["scenario-maker-sdxl"])

    assert [item.relative for item in files] == [
        "CONTEXT.md",
        "references/models/sdxl.md",
        "references/routing.md",
    ]
    assert all(item.size > 0 for item in files)


def test_skill_files_reject_symlink_escapes_and_cycles(roots, tmp_path):
    first, _ = roots
    skill = first / "scenario-maker-wan"
    outside = tmp_path / "private.md"
    outside.write_text("private\n", encoding="utf-8")
    symlink(skill / "leak.md", outside)
    symlink(skill / "loop", skill)
    discovery = discover_skills([str(first)], None)

    files = skill_files(discovery.skills["scenario-maker-wan"])

    assert [item.relative for item in files] == []


def test_selection_parsing_orders_and_validates_entries():
    entries = parse_selection(
        "\n  scenario-maker-sdxl/references/routing.md \n\nscenario-maker-wan\n"
        "scenario-maker-sdxl\nscenario-maker-sdxl/references/routing.md\n"
    )
    assert [(entry.skill, entry.file) for entry in entries] == [
        ("scenario-maker-sdxl", "references/routing.md"),
        ("scenario-maker-wan", None),
        ("scenario-maker-sdxl", None),
        ("scenario-maker-sdxl", "references/routing.md"),
    ]
    assert prompt_assistant.group_selection(entries) == {
        "scenario-maker-sdxl": ["references/routing.md"],
        "scenario-maker-wan": [],
    }
    assert parse_selection("") == []


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("sdxl\\references\\a.md", "must use / as the separator"),
        ("/sdxl", "must start with a skill name"),
        ("../sdxl", "must start with a skill name"),
        (".hidden", "must start with a skill name"),
        ("sdxl/../other/a.md", "must stay inside its skill"),
        ("sdxl/references/./a.md", "must stay inside its skill"),
        ("sdxl//a.md", "must stay inside its skill"),
        ("sdxl/.git/a.md", "hidden directory"),
        ("sdxl/evals/snapshot/SKILL.md", "excluded directory evals/"),
        ("sdxl/docs/a.md", "excluded directory docs/"),
        ("sdxl/SKILL.md", "attached by the bare skill name"),
        ("sdxl/references/data.csv", "must name a .md file"),
        ("sdxl/references/", "must stay inside its skill"),
    ],
)
def test_selection_parsing_rejects_bad_entries(text, message):
    with pytest.raises(PromptAssistantError, match=message):
        parse_selection(text)


def test_selection_resolution_attaches_skill_file_and_references(roots):
    first, second = roots
    discovery = discover_skills([str(first), str(second)], None)
    attachments = resolve_selection(
        parse_selection(
            "scenario-maker-sdxl/references/models/sdxl.md\nscenario-maker-pony"
        ),
        discovery,
    )

    assert [(item.skill, item.relative) for item in attachments] == [
        ("scenario-maker-sdxl", "SKILL.md"),
        ("scenario-maker-sdxl", "references/models/sdxl.md"),
        ("scenario-maker-pony", "SKILL.md"),
    ]
    assert attachments[1].path == (
        first / "scenario-maker-sdxl" / "references" / "models" / "sdxl.md"
    ).resolve()


@pytest.mark.parametrize(
    ("text", "allowlist", "message"),
    [
        ("unknown", None, "skill unknown was not found; roots searched"),
        ("not-allowlisted", ("scenario-maker-sdxl",), "not in the prompt_assistant"),
        ("absent", ("scenario-maker-sdxl", "absent"), "skill absent was not found"),
        ("scenario-maker-sdxl/references/missing.md", None, "was not found under"),
        ("scenario-maker-sdxl/references", None, "must name a .md file"),
        ("scenario-maker-sdxl/references/models", None, "must name a .md file"),
    ],
)
def test_selection_resolution_errors_name_the_entry(roots, text, allowlist, message):
    first, _ = roots
    discovery = discover_skills([str(first)], allowlist)
    with pytest.raises(PromptAssistantError, match=message):
        resolve_selection(parse_selection(text), discovery)


def test_selection_resolution_rejects_symlink_escape(roots, tmp_path):
    first, _ = roots
    outside = tmp_path / "private.md"
    outside.write_text("private\n", encoding="utf-8")
    symlink(first / "scenario-maker-wan" / "leak.md", outside)
    discovery = discover_skills([str(first)], None)
    with pytest.raises(PromptAssistantError, match="resolves outside skill"):
        resolve_selection(parse_selection("scenario-maker-wan/leak.md"), discovery)


def test_attachments_enforce_caps_and_build_ordered_system_message(
    roots, monkeypatch
):
    first, _ = roots
    discovery = discover_skills([str(first)], None)
    attachments = resolve_selection(
        parse_selection(
            "scenario-maker-sdxl/references/routing.md\nscenario-maker-wan"
        ),
        discovery,
    )
    attached = read_attachments(attachments)
    message = build_system_message("  Master.  ", attached)

    assert message == (
        "Master.\n\n"
        "# Skill: scenario-maker-sdxl\n\n"
        "# scenario-maker-sdxl\n\nBody of scenario-maker-sdxl.\n\n"
        "## scenario-maker-sdxl/references/routing.md\n\n"
        "Reference references/routing.md\n\n"
        "# Skill: scenario-maker-wan\n\n"
        "# scenario-maker-wan\n\nBody of scenario-maker-wan."
    )
    assert build_system_message("", []) is None
    assert build_system_message("Only master", []) == "Only master"

    monkeypatch.setattr(prompt_assistant, "ATTACHED_TOTAL_LIMIT", 100)
    with pytest.raises(PromptAssistantError, match="above the 0 KiB limit; largest"):
        read_attachments(attachments)

    monkeypatch.setattr(prompt_assistant, "FILE_LIMIT", 10)
    with pytest.raises(PromptAssistantError, match="SKILL.md exceeds the 0 KiB"):
        read_attachments(attachments)


def test_attachments_require_utf8(roots):
    first, _ = roots
    (first / "scenario-maker-wan" / "SKILL.md").write_bytes(b"\xff\xfe bad")
    discovery = discover_skills([str(first)], None)
    with pytest.raises(PromptAssistantError, match="must be UTF-8"):
        read_attachments(
            resolve_selection(parse_selection("scenario-maker-wan"), discovery)
        )


def test_frontmatter_stripping_is_conservative():
    assert strip_frontmatter("---\na: 1\n---\nbody\n") == "body\n"
    assert strip_frontmatter("body\n---\n") == "body\n---\n"
    assert strip_frontmatter("---\nunterminated\n") == "---\nunterminated\n"
    assert strip_frontmatter("") == ""
