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


"""A minimal Proxmox VE API client built on the standard library only.

CloudStack copies an extension onto the management server and runs it with the
system interpreter, so this package deliberately has no runtime dependencies.
"""

from __future__ import annotations

import json
import ssl
import time
from typing import Any
from urllib import error, parse, request

from .coerce import as_mapping, as_string
from .errors import ProxmoxError
from .settings import ProxmoxSettings

API_PREFIX = "/api2/json"
DEFAULT_WAIT_SECONDS = 600
DEFAULT_REQUEST_TIMEOUT = 120

#: Substrings Proxmox uses to say "this VM is gone", in any of its phrasings.
NOT_FOUND_MARKERS = (
    "not found",
    "does not exist",
    "no such vm",
    "unknown vm",
    "unable to find a virtual machine",
    "vmid not found",
)


class ProxmoxClient:
    """Performs authenticated requests against the Proxmox VE API."""

    def __init__(
        self,
        settings: ProxmoxSettings,
        wait_time: int | None = None,
        request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        self.settings = settings
        self.wait_time = (
            wait_time if wait_time and wait_time > 0 else DEFAULT_WAIT_SECONDS
        )
        self.request_timeout = request_timeout
        self._ssl_context = (
            ssl.create_default_context()
            if settings.verify_tls_certificate
            # Bypassing verification is an explicit, admin controlled choice.
            else ssl._create_unverified_context()  # noqa: S323
        )

    def call(
        self, method: str, path: str, data: dict[str, Any] | str | None = None
    ) -> dict[str, Any]:
        """Send a request and return the decoded JSON body.

        Raises:
            ProxmoxError: The request failed or the response was not a JSON object.
        """
        url = f"{self.settings.url}{API_PREFIX}{path}"
        headers = {"Authorization": self.settings.auth_header}
        body: bytes | None
        if data is None:
            body = None
        elif isinstance(data, str):
            body = data.encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = parse.urlencode(data, doseq=True).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        # The base URL is normalized to http(s) when the settings are parsed.
        req = request.Request(  # noqa: S310
            url, data=body, headers=headers, method=method.upper()
        )
        try:
            with request.urlopen(  # noqa: S310
                req,
                context=self._ssl_context,
                timeout=self.request_timeout,
            ) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise ProxmoxError(
                extract_error_message(raw, exc.code, exc.reason)
            ) from exc
        except error.URLError as exc:
            raise ProxmoxError(as_string(getattr(exc, "reason", exc))) from exc

        if not raw.strip():
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProxmoxError(
                f"Invalid JSON response from Proxmox API: {raw}"
            ) from exc
        if not isinstance(parsed, dict):
            raise ProxmoxError("Invalid response from Proxmox API")
        return parsed

    def call_and_wait(
        self, method: str, path: str, data: dict[str, Any] | str | None = None
    ) -> None:
        """Send a request that starts a Proxmox task and wait for it to finish."""
        response = self.call(method, path, data)
        upid = as_string(response.get("data"))
        if not upid:
            message = as_string(response.get("error")) or as_string(
                response.get("message"), "Unknown error"
            )
            raise ProxmoxError(
                f"Failed to execute API or retrieve UPID. Message: {message}"
            )
        self.wait_for_task(upid)

    def wait_for_task(
        self, upid: str, timeout: int | None = None, interval: int = 1
    ) -> None:
        """Poll a task until it stops, or raise once ``timeout`` seconds elapse."""
        timeout = self.wait_time if timeout is None or timeout <= 0 else timeout
        deadline = time.monotonic() + timeout
        node = self.settings.node
        task_path = f"/nodes/{node}/tasks/{parse.quote(upid, safe='')}/status"
        while True:
            if time.monotonic() > deadline:
                raise ProxmoxError("Timeout while waiting for async task")
            status_data = as_mapping(self.call("GET", task_path).get("data"))
            if as_string(status_data.get("status")).lower() == "stopped":
                exit_status = as_string(status_data.get("exitstatus"))
                if exit_status and exit_status != "OK":
                    raise ProxmoxError(f"Task failed with exit status: {exit_status}")
                return
            time.sleep(interval)


def extract_error_message(raw: str, status_code: int, reason: str | None) -> str:
    """Pull a human readable message out of a Proxmox error response body."""
    fallback = f"HTTP {status_code}{': ' + reason if reason else ''}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return f"{fallback}: {raw.strip() or 'Unknown error'}"
    if isinstance(parsed, dict):
        for key in ("message", "error"):
            value = parsed.get(key)
            if value:
                return as_string(value)
        errors = parsed.get("errors")
        if errors:
            return as_string(errors)
    return f"{fallback}: {raw.strip() or 'Unknown error'}"


def is_not_found(exc: ProxmoxError) -> bool:
    """Report whether ``exc`` means the VM no longer exists."""
    message = str(exc).lower()
    return any(marker in message for marker in NOT_FOUND_MARKERS)
