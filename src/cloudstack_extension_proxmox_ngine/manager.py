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


"""The CloudStack extension operations, expressed against the Proxmox API.

Every operation returns the JSON document CloudStack expects and raises
:class:`~cloudstack_extension_proxmox_ngine.errors.ProxmoxError` on failure, so
the command line layer stays a thin printer.
"""

from __future__ import annotations

import contextlib
import re
from pathlib import Path
from typing import Any

from .client import ProxmoxClient, is_not_found
from .coerce import as_list, as_mapping, as_string, format_snapshot_time
from .errors import ProxmoxError
from .settings import ProxmoxSettings, load_settings

#: Proxmox rejects anything else, and CloudStack names are not pre-validated.
NAME_PATTERN = re.compile(r"^[a-zA-Z0-9-]+$")

POWER_STATES = {"running": "poweron", "stopped": "poweroff"}


class ProxmoxManager:
    """Runs a single extension operation against one Proxmox node."""

    def __init__(
        self, settings: ProxmoxSettings, client: ProxmoxClient | None = None
    ) -> None:
        self.settings = settings
        self.client = client if client is not None else ProxmoxClient(settings)

    @classmethod
    def from_config_file(
        cls, config_path: str | Path, wait_time: int | None = None
    ) -> ProxmoxManager:
        """Build a manager from the JSON payload CloudStack wrote to disk."""
        settings = load_settings(config_path)
        return cls(settings, ProxmoxClient(settings, wait_time=wait_time))

    # -- helpers ---------------------------------------------------------

    @property
    def _vm_path(self) -> str:
        return f"/nodes/{self.settings.node}/qemu/{self.settings.vmid}"

    def _require(self, **fields: Any) -> None:
        missing = [name for name, value in fields.items() if value in (None, "", 0)]
        if missing:
            raise ProxmoxError(f"Missing required fields: {' '.join(missing)}")

    @staticmethod
    def _validate_name(kind: str, name: str) -> None:
        if not NAME_PATTERN.fullmatch(name):
            raise ProxmoxError(
                f"Invalid {kind} name '{name}'. "
                "Only alphanumeric characters and dashes (-) are allowed."
            )

    def _vm_not_present(self) -> bool:
        try:
            self.client.call("GET", f"{self._vm_path}/status/current")
        except ProxmoxError as exc:
            return is_not_found(exc)
        return False

    def _snapshot_name(self) -> str:
        if not self.settings.snap_name:
            raise ProxmoxError("Missing required field in JSON: snap_name")
        self._validate_name("Snapshot", self.settings.snap_name)
        return self.settings.snap_name

    # -- lifecycle -------------------------------------------------------

    def prepare(self) -> dict[str, Any]:
        """Reserve the next free VM ID and hand it back to CloudStack."""
        response = self.client.call("GET", "/cluster/nextid")
        vmid = as_string(response.get("data"))
        if not vmid:
            raise ProxmoxError(
                as_string(
                    response.get("message"), "Unable to retrieve next available VM ID"
                )
            )
        return {"details": {"proxmox_vmid": vmid}}

    def create(self) -> dict[str, Any]:
        """Create the VM from an ISO or a template, attach its NICs and start it."""
        settings = self.settings
        vm_name = settings.vm_name or settings.vm_internal_name
        if not vm_name:
            raise ProxmoxError("Missing required fields: vm_internal_name")
        self._validate_name("VM", vm_name)
        self._require(
            vmid=settings.vmid,
            network_bridge=settings.network_bridge,
            vmcpus=settings.vmcpus,
            vmmemory=settings.vmmemory,
        )

        from_iso = settings.template_type.strip().upper() == "ISO"
        self._validate_source_fields(from_iso)

        created = False
        try:
            created = True
            if from_iso:
                self._create_from_iso(vm_name)
            else:
                self._create_from_template(vm_name)
            self._configure_networks()
            self.client.call_and_wait("POST", f"{self._vm_path}/status/start")
        except ProxmoxError:
            if created:
                self._cleanup_created_vm()
            raise
        except Exception as exc:
            if created:
                self._cleanup_created_vm()
            raise ProxmoxError(str(exc)) from exc
        return {"status": "success", "message": "Instance created"}

    def _validate_source_fields(self, from_iso: bool) -> None:
        """Check the source specific fields before anything is created."""
        settings = self.settings
        if from_iso:
            if not settings.iso_path:
                raise ProxmoxError("Missing required field in JSON: iso_path")
            if not settings.disk_size_gb:
                raise ProxmoxError("Missing required field in JSON: disk_size_gb")
        elif not settings.template_id:
            raise ProxmoxError("Missing required field in JSON: template_id")

    def _create_from_iso(self, vm_name: str) -> None:
        settings = self.settings
        payload = {
            "vmid": settings.vmid,
            "name": vm_name,
            "ide2": f"{settings.iso_path},media=cdrom",
            "ostype": settings.iso_os_type,
            "scsihw": "virtio-scsi-single",
            "scsi0": f"{settings.storage}:{settings.disk_size_gb},iothread=on",
            "sockets": 1,
            "cores": settings.vmcpus,
            "numa": 0,
            "cpu": "x86-64-v2-AES",
            "memory": self._memory_mb(),
        }
        self.client.call_and_wait("POST", f"/nodes/{settings.node}/qemu/", payload)

    def _create_from_template(self, vm_name: str) -> None:
        settings = self.settings
        self.client.call_and_wait(
            "POST",
            f"/nodes/{settings.node}/qemu/{settings.template_id}/clone",
            {
                "newid": settings.vmid,
                "name": vm_name,
                "storage": settings.storage,
                "full": 1 if settings.is_full_clone else 0,
            },
        )
        # A clone inherits the template sizing, so apply the service offering.
        self.client.call_and_wait(
            "POST",
            f"{self._vm_path}/config",
            {"cores": settings.vmcpus, "memory": self._memory_mb()},
        )

    def _configure_networks(self) -> None:
        settings = self.settings
        pairs = zip(settings.mac_addresses, settings.vlans, strict=False)
        for index, (mac, vlan) in enumerate(pairs):
            if not mac or not vlan:
                continue
            value = (
                f"virtio={mac},bridge={settings.network_bridge},"
                f"tag={vlan},firewall=0"
            )
            self.client.call("PUT", f"{self._vm_path}/config/", {f"net{index}": value})

    def _memory_mb(self) -> int:
        return self.settings.vmmemory // 1024 // 1024

    def _cleanup_created_vm(self) -> None:
        # A failing cleanup must never mask the error that triggered it.
        with contextlib.suppress(Exception):
            self.client.call("DELETE", self._vm_path)

    def start(self) -> dict[str, Any]:
        """Power the VM on."""
        self.client.call_and_wait("POST", f"{self._vm_path}/status/start")
        return {"status": "success", "message": "Instance started"}

    def stop(self) -> dict[str, Any]:
        """Power the VM off, treating an already deleted VM as success."""
        if self._vm_not_present():
            return {"status": "success", "message": "Instance stopped"}
        self.client.call_and_wait("POST", f"{self._vm_path}/status/stop")
        return {"status": "success", "message": "Instance stopped"}

    def reboot(self) -> dict[str, Any]:
        """Reboot the VM."""
        self.client.call_and_wait("POST", f"{self._vm_path}/status/reboot")
        return {"status": "success", "message": "Instance rebooted"}

    def delete(self) -> dict[str, Any]:
        """Destroy the VM, treating an already deleted VM as success."""
        if self._vm_not_present():
            return {"status": "success", "message": "Instance deleted"}
        self.client.call_and_wait("DELETE", self._vm_path)
        return {"status": "success", "message": "Instance deleted"}

    # -- state -----------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Report the power state of a single VM."""
        response = self.client.call("GET", f"{self._vm_path}/status/current")
        vm_status = as_string(as_mapping(response.get("data")).get("status")).lower()
        return {
            "status": "success",
            "power_state": POWER_STATES.get(vm_status, "unknown"),
        }

    def statuses(self) -> dict[str, Any]:
        """Report the power state of every non-template VM on the node."""
        response = self.client.call("GET", f"/nodes/{self.settings.node}/qemu")
        try:
            vms = as_list(response.get("data"))
        except TypeError as exc:
            raise ProxmoxError("Failed to parse VM status output") from exc
        power_state: dict[str, str] = {}
        for vm in vms:
            vm_map = as_mapping(vm)
            if vm_map.get("template") == 1:
                continue
            name = as_string(vm_map.get("name") or vm_map.get("vmid"))
            vm_status = as_string(vm_map.get("status")).lower()
            power_state[name] = POWER_STATES.get(vm_status, "unknown")
        return {"status": "success", "power_state": power_state}

    def get_console(self) -> dict[str, Any]:
        """Open a one time VNC ticket and return the console coordinates."""
        response = self.client.call("POST", f"{self._vm_path}/vncproxy")
        data = as_mapping(response.get("data"))
        port = as_string(data.get("port"))
        ticket = as_string(data.get("ticket"))
        if not port or not ticket:
            raise ProxmoxError("Proxmox response missing port/ticket")
        host = self.get_node_host()
        if not host:
            raise ProxmoxError(
                f"Could not determine host IP for node {self.settings.node}"
            )
        return {
            "status": "success",
            "message": "Console retrieved",
            "console": {
                "host": host,
                "port": port,
                "password": ticket,
                "passwordonetimeuseonly": True,
                "protocol": "vnc",
            },
        }

    def get_node_host(self) -> str:
        """Find the address to reach the node on, preferring physical interfaces."""
        try:
            response = self.client.call("GET", f"/nodes/{self.settings.node}/network")
        except ProxmoxError:
            return ""
        try:
            interfaces = as_list(response.get("data"))
        except TypeError:
            return ""
        return _first_address(interfaces, physical_only=True) or _first_address(
            interfaces, physical_only=False
        )

    # -- snapshots -------------------------------------------------------

    def list_snapshots(self) -> dict[str, Any]:
        """List the VM snapshots, with timestamps rendered for humans."""
        response = self.client.call("GET", f"{self._vm_path}/snapshot")
        try:
            snapshots = as_list(response.get("data"))
        except TypeError as exc:
            raise ProxmoxError("Failed to parse snapshot output") from exc
        formatted = [
            {
                "name": as_string(snap.get("name")),
                "snaptime": format_snapshot_time(snap.get("snaptime")),
                "description": snap.get("description"),
                "parent": as_string(snap.get("parent") or "-"),
                "vmstate": as_string(snap.get("vmstate") or "-"),
            }
            for snap in map(as_mapping, snapshots)
        ]
        return {"status": "success", "printmessage": "true", "message": formatted}

    def create_snapshot(self) -> dict[str, Any]:
        """Snapshot the VM, optionally including its memory state."""
        snap_name = self._snapshot_name()
        payload: dict[str, Any] = {
            "snapname": snap_name,
            "vmstate": 1 if self.settings.snap_save_memory else 0,
        }
        if self.settings.snap_description:
            payload["description"] = self.settings.snap_description
        self.client.call_and_wait("POST", f"{self._vm_path}/snapshot", payload)
        return {"status": "success", "message": "Instance Snapshot created"}

    def restore_snapshot(self) -> dict[str, Any]:
        """Roll the VM back to a snapshot and start it again if needed."""
        snap_name = self._snapshot_name()
        self.client.call_and_wait(
            "POST", f"{self._vm_path}/snapshot/{snap_name}/rollback"
        )
        # Rolling back a snapshot without memory state leaves the VM stopped.
        try:
            response = self.client.call("GET", f"{self._vm_path}/status/current")
            vm_status = as_string(
                as_mapping(response.get("data")).get("status")
            ).lower()
            if vm_status == "stopped":
                self.client.call_and_wait("POST", f"{self._vm_path}/status/start")
        except ProxmoxError:
            pass
        return {"status": "success", "message": "Instance Snapshot restored"}

    def delete_snapshot(self) -> dict[str, Any]:
        """Delete a snapshot of the VM."""
        snap_name = self._snapshot_name()
        self.client.call_and_wait("DELETE", f"{self._vm_path}/snapshot/{snap_name}")
        return {"status": "success", "message": "Instance Snapshot deleted"}


def _first_address(interfaces: list[Any], physical_only: bool) -> str:
    """Return the first usable address, skipping bridges when asked to."""
    for entry in map(as_mapping, interfaces):
        if physical_only:
            if as_string(entry.get("type")).lower() in {"bridge", "bond"}:
                continue
            if as_string(entry.get("method")).lower() != "static":
                continue
        address = as_string(entry.get("address"))
        if address:
            return address
        cidr = as_string(entry.get("cidr"))
        if cidr:
            return cidr.split("/")[0]
    return ""
