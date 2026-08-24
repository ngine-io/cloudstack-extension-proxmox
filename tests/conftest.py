"""Shared fixtures: a recording fake client and a representative payload."""

from __future__ import annotations

import json
from typing import Any

import pytest

from cloudstack_extension_proxmox_ngine.errors import ProxmoxError
from cloudstack_extension_proxmox_ngine.manager import ProxmoxManager
from cloudstack_extension_proxmox_ngine.settings import ProxmoxSettings, parse_settings


class FakeClient:
    """Stands in for :class:`ProxmoxClient` and records every call."""

    def __init__(
        self,
        responses: dict[str, Any] | None = None,
        errors: dict[str, Exception] | None = None,
    ) -> None:
        self.responses = responses or {}
        self.errors = errors or {}
        self.calls: list[tuple[str, str, Any]] = []
        self.waited: list[tuple[str, str, Any]] = []

    def _resolve(self, method: str, path: str) -> Any:
        for key, exc in self.errors.items():
            if key in path:
                raise exc
        for key, response in self.responses.items():
            if key in path:
                return response
        return {"data": "UPID:node:0000:qmstart:100:root@pam:"}

    def call(self, method: str, path: str, data: Any = None) -> dict[str, Any]:
        self.calls.append((method, path, data))
        return self._resolve(method, path)

    def call_and_wait(self, method: str, path: str, data: Any = None) -> None:
        self.calls.append((method, path, data))
        self.waited.append((method, path, data))
        self._resolve(method, path)

    def paths(self, method: str | None = None) -> list[str]:
        return [p for m, p, _ in self.calls if method is None or m == method]


@pytest.fixture
def payload() -> dict[str, Any]:
    """A payload shaped like the JSON CloudStack writes for an extension run."""
    return {
        "externaldetails": {
            "extension": {"url": "https://fallback.example.com"},
            "host": {
                "url": "pve.example.com",
                "user": "root@pam",
                "token": "cloudstack",
                "secret": "s3cr3t",
                "node": "pve1",
                "network_bridge": "vmbr0",
                "verify_tls_certificate": "false",
            },
            "virtualmachine": {
                "template_type": "TEMPLATE",
                "template_id": "9000",
                "storage": "local-lvm",
                "is_full_clone": "true",
            },
        },
        "cloudstack.vm.details": {
            "name": "i-2-3-VM",
            "cpus": "2",
            "minRam": "2147483648",
            "details": {"proxmox_vmid": "101"},
            "nics": [
                {"mac": "02:00:00:aa:bb:cc", "broadcastUri": "vlan://100"},
                {"mac": "02:00:00:aa:bb:dd", "broadcastUri": "vlan://200"},
            ],
        },
        "parameters": {"snap_name": "before-upgrade"},
    }


@pytest.fixture
def settings(payload: dict[str, Any]) -> ProxmoxSettings:
    return parse_settings(payload)


@pytest.fixture
def client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def manager(settings: ProxmoxSettings, client: FakeClient) -> ProxmoxManager:
    return ProxmoxManager(settings, client)


@pytest.fixture
def config_file(tmp_path, payload):
    """The payload written to disk, as CloudStack hands it to the extension."""
    path = tmp_path / "payload.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


__all__ = ["FakeClient", "ProxmoxError"]
