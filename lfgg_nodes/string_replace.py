import re

TEXT_LIMIT = 1024 * 1024
SEARCH_LIMIT = 4 * 1024
OUTPUT_LIMIT = 1024 * 1024


class StringReplaceError(ValueError):
    pass


def _utf8_size(value, label, limit):
    if type(value) is not str:
        raise StringReplaceError(f"{label} must be a string")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        raise StringReplaceError(f"{label} must be valid UTF-8 text") from None
    if size > limit:
        raise StringReplaceError(f"{label} exceeds the {limit} byte limit")


def _validate_inputs(text, search, replacement, case_sensitive):
    _utf8_size(text, "text", TEXT_LIMIT)
    _utf8_size(search, "search", SEARCH_LIMIT)
    _utf8_size(replacement, "replacement", TEXT_LIMIT)
    if type(case_sensitive) is not bool:
        raise StringReplaceError("case_sensitive must be Boolean")


def _build_output(matches, text, replacement):
    chunks = []
    output_size = 0
    end = 0
    for match in matches:
        prefix = text[end : match.start()]
        prefix_size = len(prefix.encode("utf-8"))
        if output_size + prefix_size > OUTPUT_LIMIT:
            raise StringReplaceError(
                f"replaced text exceeds the {OUTPUT_LIMIT} byte limit"
            )
        chunks.append(prefix)
        output_size += prefix_size
        replacement_text = replacement(match, OUTPUT_LIMIT - output_size)
        replacement_size = len(replacement_text.encode("utf-8"))
        if output_size + replacement_size > OUTPUT_LIMIT:
            raise StringReplaceError(
                f"replaced text exceeds the {OUTPUT_LIMIT} byte limit"
            )
        chunks.append(replacement_text)
        output_size += replacement_size
        end = match.end()
    suffix = text[end:]
    suffix_size = len(suffix.encode("utf-8"))
    if output_size + suffix_size > OUTPUT_LIMIT:
        raise StringReplaceError(f"replaced text exceeds the {OUTPUT_LIMIT} byte limit")
    chunks.append(suffix)
    return "".join(chunks)


def _replace_literal(text, search, replacement, case_sensitive):
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(re.escape(search), flags)
    return _build_output(
        pattern.finditer(text), text, lambda _match, _remaining: replacement
    )


def _replacement_bound(match, replacement):
    bound = len(replacement.encode("utf-8"))
    index = 0
    while index < len(replacement):
        if replacement[index] != "\\" or index + 1 == len(replacement):
            index += 1
            continue
        token = replacement[index + 1]
        if token == "\\":
            index += 2
            continue
        reference_start = index
        if (
            token == "g"
            and index + 2 < len(replacement)
            and replacement[index + 2] == "<"
        ):
            end = replacement.find(">", index + 3)
            if end == -1:
                break
            group = replacement[index + 3 : end]
            index = end + 1
        elif token in "123456789":
            if (
                index + 3 < len(replacement)
                and all(
                    digit in "01234567"
                    for digit in replacement[index + 1 : index + 4]
                )
            ):
                # Three-digit numeric escapes are octal, not capture references.
                index += 4
                continue
            end = index + 2
            if end < len(replacement) and replacement[end].isdigit():
                end += 1
            group = replacement[index + 1 : end]
            index = end
        else:
            index += 2
            continue
        try:
            value = match.group(int(group) if group.isdecimal() else group) or ""
        except IndexError:
            continue
        bound += len(value.encode("utf-8")) - len(
            replacement[reference_start:index].encode("utf-8")
        )
    return bound


def _expand_regex_replacement(match, replacement, remaining):
    if _replacement_bound(match, replacement) > remaining:
        raise StringReplaceError(f"replaced text exceeds the {OUTPUT_LIMIT} byte limit")
    return match.expand(replacement)


def _replace_regex(text, search, replacement, case_sensitive):
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        pattern = re.compile(search, flags)
    except (re.error, RecursionError, OverflowError) as error:
        message = getattr(error, "msg", str(error))
        raise StringReplaceError(f"invalid regex search: {message}") from None
    try:
        pattern.sub(replacement, "")
    except re.error as error:
        raise StringReplaceError(f"invalid regex replacement: {error}") from None
    return _build_output(
        pattern.finditer(text),
        text,
        lambda match, remaining: _expand_regex_replacement(
            match, replacement, remaining
        ),
    )


class StringReplace:
    CATEGORY = "LFGG/text"
    DESCRIPTION = "Replaces every literal search match in text."
    FUNCTION = "replace"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    OUTPUT_TOOLTIPS = ("Text after every replacement.",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
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

    def replace(self, text, search, replacement, case_sensitive=True):
        _validate_inputs(text, search, replacement, case_sensitive)
        if not search:
            return (text,)
        return (_replace_literal(text, search, replacement, case_sensitive),)


class StringReplaceRegex:
    CATEGORY = "LFGG/text"
    DESCRIPTION = "Replaces every literal or regular-expression search match in text."
    FUNCTION = "replace"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    OUTPUT_TOOLTIPS = ("Text after every replacement.",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
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

    def replace(self, text, search, replacement, use_regex=True, case_sensitive=True):
        _validate_inputs(text, search, replacement, case_sensitive)
        if type(use_regex) is not bool:
            raise StringReplaceError("use_regex must be Boolean")
        if not search:
            return (text,)
        if use_regex:
            return (_replace_regex(text, search, replacement, case_sensitive),)
        return (_replace_literal(text, search, replacement, case_sensitive),)
