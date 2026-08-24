from __future__ import annotations

import datetime as dt

import pytest

from cloudstack_extension_proxmox_ngine import coerce


@pytest.mark.parametrize(
    ("value", "expected"),
    [({"a": 1}, {"a": 1}), (None, {}), ("text", {}), ([1], {})],
)
def test_as_mapping_only_passes_through_dicts(value, expected):
    assert coerce.as_mapping(value) == expected


@pytest.mark.parametrize("value", [None, "", "null"])
def test_as_list_treats_null_markers_as_empty(value):
    assert coerce.as_list(value) == []


def test_as_list_wraps_a_single_mapping():
    assert coerce.as_list({"vmid": 100}) == [{"vmid": 100}]


def test_as_list_rejects_unexpected_types():
    with pytest.raises(TypeError):
        coerce.as_list("not-a-list")


@pytest.mark.parametrize(
    ("value", "expected"),
    [("text", "text"), (None, ""), (7, "7"), (True, "True")],
)
def test_as_string(value, expected):
    assert coerce.as_string(value) == expected


def test_as_string_uses_the_default_for_none_only():
    assert coerce.as_string(None, "-") == "-"
    assert coerce.as_string("", "-") == ""


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("true", True),
        ("TRUE", True),
        (" yes ", True),
        ("on", True),
        ("1", True),
        (1, True),
        ("false", False),
        ("no", False),
        ("", False),
        (True, True),
        (False, False),
    ],
)
def test_as_bool(value, expected):
    assert coerce.as_bool(value) is expected


def test_as_bool_falls_back_to_the_default_when_missing():
    assert coerce.as_bool(None, True) is True


@pytest.mark.parametrize(
    ("value", "expected"),
    [("42", 42), (42, 42), ("", 0), (None, 0), ("abc", 0), (3.9, 3)],
)
def test_as_int(value, expected):
    assert coerce.as_int(value) == expected


def test_as_int_uses_the_default_for_unparseable_values():
    assert coerce.as_int("abc", 600) == 600


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("pve.example.com", "https://pve.example.com"),
        ("  https://pve.example.com/  ", "https://pve.example.com"),
        ("http://pve.example.com:8006/", "http://pve.example.com:8006"),
    ],
)
def test_normalize_url(value, expected):
    assert coerce.normalize_url(value) == expected


def test_format_snapshot_time_renders_an_epoch_in_local_time():
    expected = dt.datetime.fromtimestamp(1_700_000_000).strftime("%Y-%m-%d %H:%M:%S")
    assert coerce.format_snapshot_time(1_700_000_000) == expected
    assert coerce.format_snapshot_time("1700000000") == expected


@pytest.mark.parametrize("value", [None, "", "-"])
def test_format_snapshot_time_marks_missing_values(value):
    assert coerce.format_snapshot_time(value) == "-"


def test_format_snapshot_time_keeps_unparseable_values():
    assert coerce.format_snapshot_time("yesterday") == "yesterday"
