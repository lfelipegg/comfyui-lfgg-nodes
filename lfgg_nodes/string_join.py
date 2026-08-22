TEXT_LIMIT = 1024 * 1024


class StringJoinError(ValueError):
    pass


def _utf8_size(value, label):
    if type(value) is not str:
        raise StringJoinError(f"{label} must be a string")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        raise StringJoinError(f"{label} must be valid UTF-8 text") from None
    if size > TEXT_LIMIT:
        raise StringJoinError(f"{label} exceeds the {TEXT_LIMIT} byte limit")
    return size


class StringJoin:
    CATEGORY = "LFGG/text"
    DESCRIPTION = "Joins supplied text inputs in order with a literal separator."
    FUNCTION = "join"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    OUTPUT_TOOLTIPS = ("Joined text.",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "separator": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "Literal text placed between supplied inputs.",
                    },
                )
            },
            "optional": {
                f"text_{index}": (
                    "STRING",
                    {"forceInput": True, "tooltip": "Ordered text input."},
                )
                for index in range(1, 33)
            },
        }

    def join(self, separator, **kwargs):
        separator_size = _utf8_size(separator, "separator")
        unsupported = set(kwargs).difference(f"text_{index}" for index in range(1, 33))
        if unsupported:
            raise StringJoinError(
                "LFGG String Join received unsupported input "
                f"'{sorted(unsupported)[0]}'"
            )
        values = []
        output_size = 0
        for index in range(1, 33):
            name = f"text_{index}"
            if name in kwargs:
                value = kwargs[name]
                output_size += _utf8_size(value, name)
                values.append(value)
        output_size += separator_size * max(len(values) - 1, 0)
        if output_size > TEXT_LIMIT:
            raise StringJoinError(f"joined text exceeds the {TEXT_LIMIT} byte limit")
        return (separator.join(values),)
