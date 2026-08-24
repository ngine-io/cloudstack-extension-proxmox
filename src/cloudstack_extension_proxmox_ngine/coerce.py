# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.


"""Lenient converters for the loosely typed JSON CloudStack hands to extensions.

Values arrive as strings, numbers, booleans or are missing entirely depending on
where in CloudStack they were configured, so every accessor coerces instead of
asserting a type.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def as_mapping(value: Any) -> dict[str, Any]:
    """Return ``value`` if it is a mapping, an empty mapping otherwise."""
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    """Normalize ``value`` into a list, treating null-ish markers as empty."""
    if value in (None, "", "null"):
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return value
    raise TypeError(f"Expected a list, got {type(value).__name__}")


def as_string(value: Any, default: str = "") -> str:
    """Return ``value`` as a string, falling back to ``default`` when absent."""
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)


def as_bool(value: Any, default: bool = False) -> bool:
    """Interpret ``value`` as a boolean, accepting the usual textual spellings."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return as_string(value).strip().lower() in TRUE_VALUES


def as_int(value: Any, default: int = 0) -> int:
    """Interpret ``value`` as an integer, falling back to ``default``."""
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_url(url: str) -> str:
    """Add the default scheme and strip the trailing slash from a base URL."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def format_snapshot_time(value: Any) -> str:
    """Render a Proxmox epoch snapshot timestamp as local wall clock time."""
    if value in (None, "", "-"):
        return "-"
    try:
        return dt.datetime.fromtimestamp(int(float(value))).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    except (TypeError, ValueError, OSError, OverflowError):
        return as_string(value, "-")
