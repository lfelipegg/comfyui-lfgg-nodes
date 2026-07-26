from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path


CTX_PATH = Path(__file__).with_name("ctx.py")


def load_ctx():
    spec = importlib.util.spec_from_file_location("project_ctx", CTX_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ctx = load_ctx()


class ContextRuntimeTests(unittest.TestCase):
    def test_markdown_chunking_ignores_fenced_headings_and_empty_parents(self) -> None:
        text = """# Demo

## Empty parent

### Useful section

```python
# Code comment
## Also code
```

Useful body.
"""

        chunks = ctx.split_markdown(text, {"target_chars": 1000, "max_chars": 2000})

        self.assertEqual([heading for heading, _, _ in chunks], ["Useful section"])
        self.assertIn("# Code comment", chunks[0][2])

    def test_database_path_must_stay_in_project_context_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            (root / ".codex-context").mkdir(parents=True)

            safe = ctx.db_path(root, {"db_path": ".codex-context/index.sqlite"})
            self.assertEqual(safe, (root / ".codex-context/index.sqlite").resolve())

            for unsafe in (
                "../outside.sqlite",
                str(root.parent / "outside.sqlite"),
                ".codex-context/ctx.py",
                ".codex-context/nested/index.sqlite",
            ):
                with self.subTest(unsafe=unsafe):
                    with self.assertRaises(ctx.ConfigError):
                        ctx.db_path(root, {"db_path": unsafe})

    def test_config_rejects_nonpositive_and_inconsistent_limits(self) -> None:
        invalid_values = {
            "[chunking]\ntarget_chars = 0": "target_chars",
            "[chunking]\ntarget_chars = 5000\nmax_chars = 4000": "target_chars",
            "[output]\nsearch_limit_default = 0": "search_limit_default",
            "[output]\nsearch_limit_default = 51": "search_limit_default",
            '[sources]\ninclude = "README.md"': "include",
            '[sources]\nexclude = ["build/**", 1]': "exclude",
            (
                "[chunking]\ntarget_chars = 3000\nmax_chars = 4000\n"
                "[output]\nread_max_chars_default = 5000\nread_max_chars_hard = 4000"
            ): "read_max_chars_default",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context_dir = root / ".codex-context"
            context_dir.mkdir()
            config_path = context_dir / "config.toml"
            for settings, expected in invalid_values.items():
                with self.subTest(settings=settings):
                    config_path.write_text(settings + "\n", encoding="utf-8")
                    with self.assertRaisesRegex(ctx.ConfigError, expected):
                        ctx.config(root)

    def test_cli_rejects_out_of_bounds_output_limits(self) -> None:
        parser = ctx.build_parser()
        invalid_args = [
            ["search", "query", "--limit", "0"],
            ["search", "query", "--limit", "51"],
            ["read", "1", "--max-chars", "-1"],
            ["related", "1", "--limit", "0"],
            ["recent", "--limit", "-1"],
        ]
        for args in invalid_args:
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    parser.parse_args(args)

    def test_human_read_does_not_repeat_search_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx.ensure_project_files(root)
            doc = root / "README.md"
            doc.write_text("# Demo\n\nUnique searchable context.\n", encoding="utf-8")
            cfg = ctx.config(root)
            with ctx.connect(root) as con:
                _, count = ctx.ingest_file(con, root, doc, cfg)
                con.commit()
                chunk_id = con.execute("SELECT id FROM chunks").fetchone()[0]
            args = argparse.Namespace(repo=str(root), id=chunk_id, max_chars=None, json=False)

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(ctx.cmd_read(args), 0)

            self.assertNotIn("summary:", output.getvalue())

    def test_human_commands_do_not_print_absolute_project_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            args = argparse.Namespace(repo=str(root), json=False)

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(ctx.cmd_init(args), 0)
                self.assertEqual(ctx.cmd_status(args), 0)
                ctx.cmd_doctor(args)

            self.assertTrue((root / ".codex-context/context.sqlite").exists())
            self.assertNotIn(str(root), output.getvalue())

    def test_search_output_omits_token_estimates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx.ensure_project_files(root)
            doc = root / "README.md"
            doc.write_text("# Demo\n\nUnique searchable context.\n", encoding="utf-8")
            cfg = ctx.config(root)
            with ctx.connect(root) as con:
                ctx.ingest_file(con, root, doc, cfg)
                con.commit()

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(
                    ctx.cmd_search(argparse.Namespace(repo=str(root), query="unique", limit=5, json=False)),
                    0,
                )
                self.assertEqual(
                    ctx.cmd_search(argparse.Namespace(repo=str(root), query="unique", limit=5, json=True)),
                    0,
                )

            self.assertNotIn("approx_tokens", output.getvalue())
            self.assertNotIn("tokens_estimate", output.getvalue())

    def test_oversized_markdown_splits_at_line_boundaries(self) -> None:
        rows = [f"| row {number:02d} | value |" for number in range(8)]
        text = "# Table\n\n" + "\n".join(rows) + "\n"

        chunks = ctx.split_markdown(text, {"target_chars": 45, "max_chars": 60})

        self.assertTrue(chunks[0][2].startswith("# Table"))
        for row in rows:
            self.assertEqual(sum(row in content for _, _, content in chunks), 1)

    def test_aws_credentials_are_redacted_before_indexing(self) -> None:
        access_key = "AKIA" + "A" * 16
        secret_key = "a" * 40
        text = f"AWS_ACCESS_KEY_ID={access_key}\nAWS_SECRET_ACCESS_KEY={secret_key}\n"

        redacted, count = ctx.redact_secret_like_content(text)

        self.assertEqual(count, 2)
        self.assertNotIn(access_key, redacted)
        self.assertNotIn(secret_key, redacted)

    def test_search_only_falls_back_when_fts_is_unavailable(self) -> None:
        missing = sqlite3.connect(":memory:")
        missing.row_factory = sqlite3.Row
        missing.executescript(ctx.SCHEMA)
        self.assertEqual(ctx.search_rows(missing, "context", 5), [])
        missing.close()

        broken = sqlite3.connect(":memory:")
        broken.row_factory = sqlite3.Row
        broken.executescript(ctx.SCHEMA)
        broken.execute(
            "CREATE TABLE chunks_fts "
            "(chunk_id, title, path, heading, summary, content)"
        )
        with self.assertRaises(sqlite3.OperationalError):
            ctx.search_rows(broken, "context", 5)
        broken.close()


if __name__ == "__main__":
    unittest.main()
