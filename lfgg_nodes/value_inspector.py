import base64
import dataclasses
import itertools
import json
import math
import re
import sys
import types

MAX_REPORT_BYTES = 16 * 1024
MAX_VALUE_BYTES = 8 * 1024
MAX_DEPTH = 4
MAX_ENTRIES = 50
MAX_LABEL_BYTES = 256
MAX_INT_BITS = 12_000

_REPORT_TRUNCATED = "<report truncated>"
_SENSITIVE_ANYWHERE = {
    "authorization",
    "cookie",
    "passwd",
    "password",
    "secret",
}
_SENSITIVE_COMPACT = {
    "accesstoken",
    "apikey",
    "authorizationheader",
    "clientsecret",
    "privatekey",
    "refreshtoken",
    "secretkey",
}
_SENSITIVE_SEQUENCES = {
    ("access", "token"),
    ("api", "key"),
    ("authorization", "header"),
    ("client", "secret"),
    ("private", "key"),
    ("refresh", "token"),
    ("secret", "access", "key"),
    ("secret", "key"),
}
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_NON_IDENTIFIER = re.compile(r"[^a-z0-9]+")
_MISSING = object()


class _Report:
    def __init__(self):
        self._content = bytearray()
        self.stopped = False

    def add(self, line):
        if self.stopped:
            return
        encoded = line.encode("utf-8", "backslashreplace")
        separator = b"\n" if self._content else b""
        marker = _REPORT_TRUNCATED.encode()
        content_limit = MAX_REPORT_BYTES - len(marker) - 1
        addition = separator + encoded
        if len(self._content) + len(addition) <= content_limit:
            self._content.extend(addition)
            return
        self._content.extend(addition[: content_limit - len(self._content)])
        self._content.extend(b"\n" + marker)
        self.stopped = True

    def text(self):
        return self._content.decode("utf-8", "ignore")


def _type_name(value):
    value_type = type(value)
    try:
        module = type.__getattribute__(value_type, "__module__")
        name = type.__getattribute__(value_type, "__qualname__")
        if type(module) is not str or type(name) is not str:
            return "<unknown type>"
        module = module[:128]
        name = name[:128]
        label = f"{module}.{name}" if module else name
    except Exception:
        return "<unknown type>"
    return "".join(" " if character.isspace() else character for character in label)[
        :256
    ]


def _bounded_text(value, limit=MAX_VALUE_BYTES):
    sample = value[: limit + 1]
    encoded = sample.encode("utf-8", "backslashreplace")
    truncated = len(value) > limit or len(encoded) > limit
    if truncated:
        encoded = encoded[:limit]
    return encoded.decode("utf-8", "ignore"), truncated


def _string_literal(value):
    text, truncated = _bounded_text(value)
    rendered = json.dumps(text, ensure_ascii=False)
    rendered, escaped_truncated = _bounded_text(rendered)
    if truncated or escaped_truncated:
        rendered += f" <truncated: string exceeds {MAX_VALUE_BYTES} UTF-8 bytes>"
    return rendered


def _field_label(value):
    text, truncated = _bounded_text(value, MAX_LABEL_BYTES)
    rendered = json.dumps(text, ensure_ascii=False)
    if truncated:
        rendered += " <truncated field name>"
    return rendered


def _bytes_literal(value):
    preview = value[:MAX_VALUE_BYTES]
    encoded = base64.b64encode(preview).decode("ascii")
    rendered = f"bytes(length={len(value)}, base64={encoded})"
    if len(value) > MAX_VALUE_BYTES:
        rendered += f" <truncated: bytes exceed {MAX_VALUE_BYTES} bytes>"
    return rendered


def _float_literal(value):
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "infinity" if value > 0 else "-infinity"
    return str(value)


def _scalar_literal(value):
    if value is None:
        return "None"
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        bit_length = int.bit_length(value)
        if bit_length > MAX_INT_BITS:
            return f"<integer omitted: bit length {bit_length} exceeds display limit>"
        return str(value)
    if type(value) is float:
        return _float_literal(value)
    if type(value) is complex:
        real = _float_literal(value.real)
        imaginary = _float_literal(value.imag)
        return f"real={real}, imaginary={imaginary}"
    if type(value) is str:
        return _string_literal(value)
    if type(value) is bytes:
        return _bytes_literal(value)
    return None


def _key_label(key):
    literal = _scalar_literal(key)
    return literal if literal is not None else f"<key: {_type_name(key)}>"


def _is_sensitive(key):
    if type(key) is not str:
        return False
    fragments = (key[:256], key[-256:])
    for fragment in fragments:
        separated = _CAMEL_BOUNDARY.sub("_", fragment).casefold()
        parts = tuple(filter(None, _NON_IDENTIFIER.split(separated)))
        if not parts:
            continue
        compact = "".join(parts)
        if (
            compact in _SENSITIVE_COMPACT
            or any(part in _SENSITIVE_ANYWHERE for part in parts)
            or parts[-1] == "token"
        ):
            return True
        for sequence in _SENSITIVE_SEQUENCES:
            width = len(sequence)
            if any(
                parts[index : index + width] == sequence
                for index in range(len(parts) - width + 1)
            ):
                return True
    return len(key) > 512


def _tensor_type():
    torch = sys.modules.get("torch")
    if type(torch) is not types.ModuleType:
        return None
    namespace = types.ModuleType.__getattribute__(torch, "__dict__")
    tensor = namespace.get("Tensor")
    if not isinstance(tensor, type):
        return None
    try:
        module = type.__getattribute__(tensor, "__module__")
        name = type.__getattribute__(tensor, "__qualname__")
        tensor_meta = type(tensor)
        meta_module = type.__getattribute__(tensor_meta, "__module__")
        meta_name = type.__getattribute__(tensor_meta, "__qualname__")
    except Exception:
        return None
    if any(
        type(value) is not str
        for value in (module, name, meta_module, meta_name)
    ):
        return None
    if (module, name, meta_module, meta_name) != (
        "torch",
        "Tensor",
        "torch._C",
        "_TensorMeta",
    ):
        return None
    return tensor


def _raw_class_attribute(value_type, name):
    try:
        mro = type.__getattribute__(value_type, "__mro__")
        for base in mro:
            namespace = type.__getattribute__(base, "__dict__")
            if name in namespace:
                return namespace[name]
    except Exception:
        pass
    return _MISSING


def _raw_instance_dict(value):
    descriptor = _raw_class_attribute(type(value), "__dict__")
    if type(descriptor) is not types.GetSetDescriptorType:
        return None
    try:
        namespace = descriptor.__get__(value, type(value))
    except Exception:
        return None
    return namespace if type(namespace) is dict else None


def _dataclass_field_names(value):
    metadata = _raw_class_attribute(type(value), "__dataclass_fields__")
    if type(metadata) is not dict:
        return None
    entries = list(itertools.islice(metadata.values(), MAX_ENTRIES + 1))
    names = []
    for field in entries[:MAX_ENTRIES]:
        if type(field) is not dataclasses.Field:
            return None
        name = object.__getattribute__(field, "name")
        field_type = object.__getattribute__(field, "_field_type")
        if type(name) is not str or field_type is not dataclasses._FIELD:
            continue
        names.append(name)
    return tuple(names), len(entries) > MAX_ENTRIES


def _tensor_metadata(value, name):
    try:
        metadata = object.__getattribute__(value, name)
        if name == "shape":
            return "[" + ", ".join(str(int(size)) for size in metadata) + "]"
        return str(metadata).replace("\r", " ").replace("\n", " ")[:256]
    except Exception:
        return "<inspection unavailable>"


def _snapshot(value, *, mapping=False):
    before = len(value)
    iterator = value.items() if mapping else iter(value)
    entries = list(itertools.islice(iterator, MAX_ENTRIES + 1))
    return entries, len(value) != before


def _format_entries(writer, value, indent, depth, seen, *, mapping=False):
    try:
        entries, mutated = _snapshot(value, mapping=mapping)
    except RuntimeError:
        writer.add(
            f"{indent}<inspection unavailable: "
            "container changed during inspection>"
        )
        return
    if not entries:
        writer.add(f"{indent}<empty>")
        return
    for index, entry in enumerate(entries[:MAX_ENTRIES]):
        if writer.stopped:
            return
        if mapping:
            key, child = entry
            label = _key_label(key)
            if _is_sensitive(key):
                writer.add(f"{indent}{label}: <redacted: {_type_name(child)}>")
                continue
        else:
            label, child = f"[{index}]", entry
        writer.add(f"{indent}{label}:")
        _format_value(writer, child, indent + "  ", depth + 1, seen)
    if len(entries) > MAX_ENTRIES:
        writer.add(f"{indent}<truncated: more than {MAX_ENTRIES} entries>")
    if mutated:
        writer.add(
            f"{indent}<inspection unavailable: "
            "container changed during inspection>"
        )


def _format_dataclass(writer, value, field_info, indent, depth, seen):
    field_names, truncated = field_info
    if not field_names:
        writer.add(f"{indent}<empty>")
        if truncated:
            writer.add(f"{indent}<truncated: more than {MAX_ENTRIES} fields>")
        return
    namespace = _raw_instance_dict(value)
    for name in field_names[:MAX_ENTRIES]:
        if writer.stopped:
            return
        label = _field_label(name)
        if len(name) > MAX_LABEL_BYTES:
            marker = (
                "<redacted: unknown type>"
                if _is_sensitive(name)
                else "<inspection unavailable>"
            )
            writer.add(f"{indent}{label}: {marker}")
            continue
        if namespace is None or name not in namespace:
            writer.add(f"{indent}{label}: <inspection unavailable>")
            continue
        child = namespace[name]
        if _is_sensitive(name):
            writer.add(
                f"{indent}{label}: <redacted: {_type_name(child)}>"
            )
            continue
        writer.add(f"{indent}{label}:")
        _format_value(writer, child, indent + "  ", depth + 1, seen)
    if truncated:
        writer.add(f"{indent}<truncated: more than {MAX_ENTRIES} fields>")


def _format_value(writer, value, indent, depth, seen):
    writer.add(f"{indent}type: {_type_name(value)}")
    if writer.stopped:
        return
    try:
        literal = _scalar_literal(value)
        if literal is not None:
            writer.add(f"{indent}value: {literal}")
            return

        tensor_type = _tensor_type()
        if tensor_type is not None and type(value) is tensor_type:
            metadata = ", ".join(
                f"{name}={_tensor_metadata(value, name)}"
                for name in ("shape", "dtype", "device", "layout")
            )
            writer.add(f"{indent}tensor: {metadata}")
            return

        field_info = _dataclass_field_names(value)
        is_dataclass = field_info is not None
        container_type = type(value)
        is_container = container_type in {dict, list, tuple, set, frozenset}
        if not is_container and not is_dataclass:
            return
        identity = id(value)
        if identity in seen:
            writer.add(f"{indent}value: <cycle>")
            return
        if depth >= MAX_DEPTH:
            writer.add(f"{indent}value: <max depth {MAX_DEPTH} reached>")
            return
        seen.add(identity)
        try:
            writer.add(f"{indent}value:")
            if container_type is dict:
                _format_entries(
                    writer,
                    value,
                    indent + "  ",
                    depth,
                    seen,
                    mapping=True,
                )
            elif container_type in {list, tuple, set, frozenset}:
                _format_entries(writer, value, indent + "  ", depth, seen)
            else:
                _format_dataclass(
                    writer,
                    value,
                    field_info,
                    indent + "  ",
                    depth,
                    seen,
                )
        finally:
            seen.remove(identity)
    except Exception:
        writer.add(f"{indent}<inspection unavailable: {_type_name(value)}>")


def format_scheduled_values(values):
    writer = _Report()
    if type(values) is not list:
        values = [values]
    if not values:
        writer.add("scheduled values: 0")
        writer.add("value: <empty>")
    elif len(values) == 1:
        _format_value(writer, values[0], "", 0, set())
    else:
        writer.add(f"scheduled values: {len(values)}")
        seen = set()
        for index, value in enumerate(values, 1):
            if writer.stopped:
                break
            writer.add(f"item {index}:")
            _format_value(writer, value, "  ", 0, seen)
    return writer.text()


class ValueInspector:
    CATEGORY = "LFGG/debug"
    DESCRIPTION = "Displays a bounded diagnostic report for any connected value."
    FUNCTION = "inspect_value"
    RETURN_TYPES = ()
    INPUT_IS_LIST = True
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "value": (
                    "*",
                    {"tooltip": "Value to inspect after workflow execution."},
                )
            }
        }

    def inspect_value(self, value):
        return {
            "ui": {"report": [format_scheduled_values(value)]},
            "result": (),
        }
