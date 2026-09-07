# LFGG Prompt Composer

Write the prompt in the multiline `prompt_template` box. Use **Insert wildcard**
to insert `__folder/name__` at the caret, or **Insert style** to insert
`[[style:Exact Name]]`. The selectors are editing controls only; the template
and seed are the persisted inputs. Empty wildcard files and CSV rows with no
positive or negative value are shown disabled. Search filters either selector
inside the dropdown after it opens.
Insertion replaces selected text when a selection exists; each selector exposes
this guidance in its tooltip and accessible description. Refresh and usable
entry counts share a compact row that wraps at narrow node widths. Loading,
empty, and disabled-only libraries cannot be selected. Refresh progress or
failure appears beside the refresh action without replacing the template or
the last valid library choices.

Configure one styles CSV and one wildcard root in
`<ComfyUI user directory>/lfgg_nodes/config.json`:

```json
{
  "prompt_composer": {
    "styles_csv": "/absolute/path/styles.csv",
    "wildcards": "/absolute/path/wildcards"
  }
}
```

Both paths must be absolute. The CSV header must be
`name,prompt,negative_prompt`. Wildcard tokens use relative paths beneath the
configured root and omit `.txt`. Click **Refresh libraries** after changing the
configuration or source files; a failed refresh preserves the last valid
selector contents.
New nodes share the session's last valid catalog and in-flight requests.
Refresh fetches a new shared snapshot for the requesting selectors and later
nodes; existing templates and execution-time file change detection are unaffected.

Each file-wildcard occurrence draws independently from its file, while the
same template, files, and seed reproduce the same sequence. Blank wildcard
lines are ignored and duplicate lines add selection weight. Style positive
text is inserted at the token position; non-empty negative fragments are
joined in encounter order on the second output. Native `{red|blue}` dynamic
prompts remain available. Prefix a file or style token with `\` to emit it
literally without the backslash.

Missing tokens, headings used as tokens, empty wildcard files, invalid UTF-8,
unsafe paths, and invalid catalogs fail with an actionable error. The node
reads only its fixed user configuration and the configured local libraries; it
makes no network requests and writes no files. Refresh visits at most 10,000
wildcard-library entries, including directories and non-`.txt` files; the
styles CSV is limited to 4 MiB and each decoded field to 128 KiB.
