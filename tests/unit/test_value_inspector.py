import builtins
import dataclasses
import importlib.util
import math
import sys
import types
from pathlib import Path

import pytest

SOURCE = Path(__file__).parents[2] / "lfgg_nodes" / "value_inspector.py"
SPEC = importlib.util.spec_from_file_location("value_inspector", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
MAX_DEPTH = MODULE.MAX_DEPTH
MAX_ENTRIES = MODULE.MAX_ENTRIES
MAX_REPORT_BYTES = MODULE.MAX_REPORT_BYTES
MAX_VALUE_BYTES = MODULE.MAX_VALUE_BYTES
ValueInspector = MODULE.ValueInspector
format_scheduled_values = MODULE.format_scheduled_values


def test_schema_and_scheduled_values_are_exact():
    assert ValueInspector.CATEGORY == "LFGG/debug"
    assert ValueInspector.DESCRIPTION == (
        "Displays a bounded diagnostic report for any connected value."
    )
    assert ValueInspector.FUNCTION == "inspect_value"
    assert ValueInspector.RETURN_TYPES == ()
    assert ValueInspector.INPUT_IS_LIST is True
    assert ValueInspector.OUTPUT_NODE is True
    assert ValueInspector.INPUT_TYPES() == {
        "required": {
            "value": (
                "*",
                {"tooltip": "Value to inspect after workflow execution."},
            )
        }
    }

    node = ValueInspector()
    assert node.inspect_value([42]) == {
        "ui": {"report": ["type: builtins.int\nvalue: 42"]},
        "result": (),
    }
    assert format_scheduled_values([]) == "scheduled values: 0\nvalue: <empty>"
    assert format_scheduled_values([1, "two"]) == (
        "scheduled values: 2\n"
        "item 1:\n"
        "  type: builtins.int\n"
        "  value: 1\n"
        "item 2:\n"
        "  type: builtins.str\n"
        '  value: "two"'
    )


def test_safe_structures_redact_secrets_and_do_not_call_unknown_repr():
    class Dangerous:
        def __repr__(self):
            raise AssertionError("repr must not be called")

    @dataclasses.dataclass
    class Payload:
        name: str
        api_key: str

    cycle = {}
    cycle["self"] = cycle
    report = format_scheduled_values(
        [
            {
                "password": "visible only by mistake",
                "payload": Payload("demo", "also secret"),
                "cycle": cycle,
                "unknown": Dangerous(),
                ("complex", "key"): 3,
            }
        ]
    )

    assert '"password": <redacted: builtins.str>' in report
    assert "visible only by mistake" not in report
    assert '"api_key": <redacted: builtins.str>' in report
    assert "also secret" not in report
    assert "value: <cycle>" in report
    assert f"type: {Dangerous.__module__}.{Dangerous.__qualname__}" in report
    assert "<key: builtins.tuple>" in report


def test_cycles_are_active_paths_not_repeated_aliases():
    cycle = []
    cycle.append(cycle)
    shared = ["same value"]

    cycle_report = format_scheduled_values([cycle])
    sibling_report = format_scheduled_values([{"left": shared, "right": shared}])
    scheduled_report = format_scheduled_values([shared, shared])

    assert cycle_report.count("value: <cycle>") == 1
    assert "value: <cycle>" not in sibling_report
    assert sibling_report.count('value: "same value"') == 2
    assert "value: <cycle>" not in scheduled_report
    assert scheduled_report.count('value: "same value"') == 2


def test_common_credential_keys_are_redacted_without_broad_substring_matches():
    credentials = {
        "accessToken": "access-value",
        "refreshToken": "refresh-value",
        "clientSecret": "client-value",
        "privateKey": "private-value",
        "authorizationHeader": "authorization-value",
        "X-API-Key": "api-value",
        "secretKey": "secret-key-value",
        "awsSecretAccessKey": "aws-camel-value",
        "aws_secret_access_key": "aws-snake-value",
        "passwordConfirmation": "password-confirmation-value",
        "passwordHash": "password-hash-value",
        "cookieHeader": "cookie-header-value",
        "secretValue": "secret-value",
        "nested": {"database_password": "password-value"},
        "tokenCount": "visible count",
        "secretary": "visible role",
        "monkey": "visible animal",
    }

    report = format_scheduled_values([credentials])

    for secret in (
        "access-value",
        "refresh-value",
        "client-value",
        "private-value",
        "authorization-value",
        "api-value",
        "secret-key-value",
        "aws-camel-value",
        "aws-snake-value",
        "password-confirmation-value",
        "password-hash-value",
        "cookie-header-value",
        "secret-value",
        "password-value",
    ):
        assert secret not in report
    assert report.count("<redacted: builtins.str>") == 14
    assert "visible count" in report
    assert "visible role" in report
    assert "visible animal" in report


def test_depth_entry_value_and_report_limits_are_explicit():
    nested = []
    current = nested
    for _ in range(MAX_DEPTH + 1):
        child = []
        current.append(child)
        current = child

    report = format_scheduled_values(
        [
            nested,
            list(range(MAX_ENTRIES + 1)),
            "é" * (MAX_VALUE_BYTES + 1),
            b"x" * (MAX_VALUE_BYTES + 1),
        ]
    )

    assert f"<max depth {MAX_DEPTH} reached>" in report
    assert f"<truncated: more than {MAX_ENTRIES} entries>" in report
    assert f"<truncated: string exceeds {MAX_VALUE_BYTES} UTF-8 bytes>" in report
    assert report.endswith("<report truncated>")
    assert len(report.encode("utf-8")) <= MAX_REPORT_BYTES

    bytes_report = format_scheduled_values([b"x" * (MAX_VALUE_BYTES + 1)])
    assert f"<truncated: bytes exceed {MAX_VALUE_BYTES} bytes>" in bytes_report
    assert len(bytes_report.encode("utf-8")) <= MAX_REPORT_BYTES


def test_special_floats_and_unavailable_dataclass_fields_are_explicit():
    @dataclasses.dataclass
    class Broken:
        value: int

    broken = object.__new__(Broken)
    getter_called = False

    def unsafe_getter(_self):
        nonlocal getter_called
        getter_called = True
        raise ValueError

    Broken.value = property(unsafe_getter)
    report = format_scheduled_values(
        [[math.nan, math.inf, -math.inf, complex(1, -2), broken]]
    )

    assert "value: nan" in report
    assert "value: infinity" in report
    assert "value: -infinity" in report
    assert "value: real=1.0, imaginary=-2.0" in report
    assert '"value": <inspection unavailable>' in report
    assert getter_called is False


def test_type_and_dataclass_detection_do_not_invoke_user_hooks():
    formatted = False

    class FormatTrap:
        def __format__(self, _spec):
            nonlocal formatted
            formatted = True
            raise AssertionError("format must not be called")

    class OddModule:
        pass

    type.__setattr__(OddModule, "__module__", FormatTrap())

    meta_accesses = []

    class HostileMeta(type):
        def __getattribute__(cls, name):
            meta_accesses.append(name)
            raise AssertionError("metaclass hook must not be called")

    class Hostile(metaclass=HostileMeta):
        pass

    hostile = Hostile()
    meta_accesses.clear()

    class InstanceTrap:
        def __getattribute__(self, _name):
            raise AssertionError("instance hook must not be called")

    report = format_scheduled_values([OddModule(), hostile, InstanceTrap()])

    assert "type: <unknown type>" in report
    assert formatted is False
    assert meta_accesses == []
    assert "type: test_value_inspector.InstanceTrap" not in report
    assert "InstanceTrap" in report


def test_fake_torch_module_and_custom_instance_hooks_are_not_invoked(monkeypatch):
    accesses = []

    class FakeTorch(types.ModuleType):
        def __getattribute__(self, name):
            accesses.append(name)
            raise AssertionError("fake torch hook must not be called")

    class Value:
        def __getattribute__(self, name):
            accesses.append(name)
            raise AssertionError("value hook must not be called")

    monkeypatch.setitem(sys.modules, "torch", FakeTorch("torch"))

    report = format_scheduled_values([Value()])

    assert "Value" in report
    assert accesses == []


def test_poisoned_torch_metadata_does_not_invoke_equality(monkeypatch):
    compared = False

    class EqualityTrap:
        def __eq__(self, _other):
            nonlocal compared
            compared = True
            raise AssertionError("metadata equality must not be called")

    class PoisonTensor:
        pass

    type.__setattr__(PoisonTensor, "__module__", EqualityTrap())
    fake_torch = types.ModuleType("torch")
    fake_torch.Tensor = PoisonTensor
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    report = format_scheduled_values([PoisonTensor()])

    assert report.startswith("type: <unknown type>")
    assert compared is False


def test_huge_type_int_key_and_dataclass_metadata_stay_bounded():
    class HugeType:
        pass

    type.__setattr__(HugeType, "__module__", "m" * 100_000)
    huge_int = 1 << (MAX_VALUE_BYTES * 4)
    huge_field_name = "field" * 100_000
    metadata = {}
    for index in range(MAX_ENTRIES + 1):
        field = dataclasses.field()
        field.name = huge_field_name if index == 0 else f"field_{index}"
        field._field_type = dataclasses._FIELD
        metadata[str(index)] = field

    class SyntheticDataclass:
        pass

    SyntheticDataclass.__dataclass_fields__ = metadata
    synthetic = SyntheticDataclass()

    report = format_scheduled_values(
        [HugeType(), huge_int, {huge_int: "integer key"}, synthetic]
    )

    assert "<integer omitted: bit length" in report
    assert "<truncated field name>" in report
    assert "<inspection unavailable>" in report
    assert f"<truncated: more than {MAX_ENTRIES} fields>" in report
    assert len(report.encode("utf-8")) <= MAX_REPORT_BYTES


def test_sensitive_keys_are_found_at_bounded_edges():
    for key, secret in (
        ("accessToken_" + "x" * 100_000, "prefix-secret"),
        ("x" * 100_000 + "_aws_secret_access_key", "suffix-secret"),
        ("x" * 100_000, "uninspected-middle-secret"),
    ):
        report = format_scheduled_values([{key: secret}])
        assert secret not in report
        assert report.count("<redacted: builtins.str>") == 1


def test_tensor_reports_metadata_without_values():
    torch = pytest.importorskip("torch")
    tensor = torch.arange(6, dtype=torch.float32).reshape(2, 3)

    report = format_scheduled_values([tensor])

    assert report.startswith("type: torch.Tensor\n")
    assert "shape=[2, 3]" in report
    assert "dtype=torch.float32" in report
    assert "device=cpu" in report
    assert "layout=torch.strided" in report
    assert "tensor([" not in report


def test_module_does_not_import_torch_eagerly(monkeypatch):
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "torch" or name.startswith("torch."):
            raise AssertionError("value inspector imported torch eagerly")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    spec = importlib.util.spec_from_file_location("lazy_value_inspector", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert "torch" not in module.__dict__
