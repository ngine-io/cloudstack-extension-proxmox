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


"""The extension payload CloudStack writes to disk, mapped onto a dataclass."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .coerce import as_bool, as_int, as_list, as_mapping, as_string, normalize_url
from .errors import ProxmoxError

REQUIRED_HOST_FIELDS = ("url", "user", "token", "secret", "node")


@dataclass(slots=True)
class ProxmoxSettings:
    """Everything a single extension invocation needs, already coerced."""

    url: str
    user: str
    token: str
    secret: str
    node: str
    network_bridge: str = ""
    verify_tls_certificate: bool = True
    vm_name: str = ""
    vm_internal_name: str = ""
    vmid: str = ""
    vmcpus: int = 0
    vmmemory: int = 0
    template_type: str = ""
    template_id: str = ""
    iso_path: str = ""
    iso_os_type: str = "l26"
    disk_size_gb: str = "64"
    storage: str = "local-lvm"
    is_full_clone: bool = False
    snap_name: str = ""
    snap_description: str = ""
    snap_save_memory: bool = False
    mac_addresses: list[str] = field(default_factory=list)
    vlans: list[str] = field(default_factory=list)

    @property
    def auth_header(self) -> str:
        """The ``Authorization`` header value for a Proxmox API token."""
        return f"PVEAPIToken={self.user}!{self.token}={self.secret}"


def load_payload(config_path: str | Path) -> dict[str, Any]:
    """Read and decode the JSON document at ``config_path``.

    Raises:
        ProxmoxError: The file is missing, unreadable or not a JSON object.
    """
    try:
        payload = json.loads(Path(config_path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProxmoxError(f"JSON file not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ProxmoxError("Invalid JSON in file") from exc
    except OSError as exc:
        raise ProxmoxError(f"Unable to read JSON file: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProxmoxError("Invalid JSON input")
    return payload


def parse_settings(payload: dict[str, Any]) -> ProxmoxSettings:
    """Build :class:`ProxmoxSettings` from a decoded CloudStack payload.

    Raises:
        ProxmoxError: One of the fields needed to reach Proxmox is missing.
    """
    externaldetails = as_mapping(payload.get("externaldetails"))
    extension = as_mapping(externaldetails.get("extension"))
    host = as_mapping(externaldetails.get("host"))
    vm = as_mapping(externaldetails.get("virtualmachine"))
    details_root = as_mapping(payload.get("cloudstack.vm.details"))
    vm_details = as_mapping(details_root.get("details"))
    parameters = as_mapping(payload.get("parameters"))

    # Host level configuration wins over the extension wide defaults.
    url = as_string(host.get("url") or extension.get("url"))
    user = as_string(host.get("user") or extension.get("user"))
    token = as_string(host.get("token") or extension.get("token"))
    secret = as_string(host.get("secret") or extension.get("secret"))
    node = as_string(host.get("node"))

    missing = [
        name
        for name, value in zip(
            REQUIRED_HOST_FIELDS, (url, user, token, secret, node), strict=True
        )
        if not value
    ]
    if missing:
        raise ProxmoxError(f"Missing required fields: {' '.join(missing)}")

    mac_addresses: list[str] = []
    vlans: list[str] = []
    try:
        nics = as_list(details_root.get("nics"))
    except TypeError:  # A malformed nic list is not worth failing the operation.
        nics = []
    for nic in nics:
        nic_map = as_mapping(nic)
        mac_addresses.append(as_string(nic_map.get("mac")))
        vlans.append(as_string(nic_map.get("broadcastUri")).removeprefix("vlan://"))

    return ProxmoxSettings(
        url=normalize_url(url),
        user=user,
        token=token,
        secret=secret,
        node=node,
        network_bridge=as_string(host.get("network_bridge")),
        verify_tls_certificate=as_bool(
            host.get("verify_tls_certificate", "true"), True
        ),
        vm_name=as_string(vm.get("vm_name") or details_root.get("name")),
        vm_internal_name=as_string(details_root.get("name")),
        vmid=as_string(vm_details.get("proxmox_vmid")),
        vmcpus=as_int(details_root.get("cpus")),
        vmmemory=as_int(details_root.get("minRam")),
        template_type=as_string(vm.get("template_type")),
        template_id=as_string(vm.get("template_id")),
        iso_path=as_string(vm.get("iso_path")),
        iso_os_type=as_string(vm.get("iso_os_type", "l26")),
        disk_size_gb=as_string(vm.get("disk_size_gb", "64")),
        storage=as_string(vm.get("storage", "local-lvm")),
        is_full_clone=as_bool(vm.get("is_full_clone", "false")),
        snap_name=as_string(parameters.get("snap_name")),
        snap_description=as_string(parameters.get("snap_description")),
        snap_save_memory=as_bool(parameters.get("snap_save_memory", False)),
        mac_addresses=mac_addresses,
        vlans=vlans,
    )


def load_settings(config_path: str | Path) -> ProxmoxSettings:
    """Read the payload at ``config_path`` and parse it into settings."""
    return parse_settings(load_payload(config_path))
