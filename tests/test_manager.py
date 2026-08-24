from __future__ import annotations

import pytest

from cloudstack_extension_proxmox_ngine.errors import ProxmoxError
from cloudstack_extension_proxmox_ngine.manager import ProxmoxManager

from .conftest import FakeClient


def build(settings, **kwargs):
    """A manager backed by a fake client seeded with ``responses``/``errors``."""
    client = FakeClient(**kwargs)
    return ProxmoxManager(settings, client), client


# -- prepare -------------------------------------------------------------


def test_prepare_returns_the_next_free_vmid(settings):
    manager, client = build(settings, responses={"/cluster/nextid": {"data": "102"}})

    assert manager.prepare() == {"details": {"proxmox_vmid": "102"}}
    assert client.paths() == ["/cluster/nextid"]


def test_prepare_fails_when_proxmox_returns_no_id(settings):
    manager, _ = build(settings, responses={"/cluster/nextid": {"message": "denied"}})

    with pytest.raises(ProxmoxError, match="denied"):
        manager.prepare()


# -- create --------------------------------------------------------------


def test_create_clones_a_template_and_applies_the_offering(settings):
    manager, client = build(settings)

    assert manager.create() == {"status": "success", "message": "Instance created"}

    clone = client.calls[0]
    assert clone[1] == "/nodes/pve1/qemu/9000/clone"
    assert clone[2] == {
        "newid": "101",
        "name": "i-2-3-VM",
        "storage": "local-lvm",
        "full": 1,
    }
    config = client.calls[1]
    assert config[1] == "/nodes/pve1/qemu/101/config"
    assert config[2] == {"cores": 2, "memory": 2048}
    assert client.calls[-1][1] == "/nodes/pve1/qemu/101/status/start"


def test_create_uses_a_linked_clone_unless_a_full_clone_is_requested(settings):
    settings.is_full_clone = False
    manager, client = build(settings)

    manager.create()

    assert client.calls[0][2]["full"] == 0


def test_create_attaches_every_nic_with_its_vlan(settings):
    manager, client = build(settings)

    manager.create()

    nic_calls = [call for call in client.calls if call[1].endswith("/config/")]
    assert [call[2] for call in nic_calls] == [
        {"net0": "virtio=02:00:00:aa:bb:cc,bridge=vmbr0,tag=100,firewall=0"},
        {"net1": "virtio=02:00:00:aa:bb:dd,bridge=vmbr0,tag=200,firewall=0"},
    ]


def test_create_skips_nics_without_a_mac_or_vlan(settings):
    settings.mac_addresses = ["02:00:00:aa:bb:cc", ""]
    settings.vlans = ["", "200"]
    manager, client = build(settings)

    manager.create()

    assert [call for call in client.calls if call[1].endswith("/config/")] == []


def test_create_from_an_iso_provisions_a_disk_and_cdrom(settings):
    settings.template_type = "iso"
    settings.iso_path = "local:iso/debian.iso"
    settings.disk_size_gb = "32"
    manager, client = build(settings)

    manager.create()

    payload = client.calls[0][2]
    assert client.calls[0][1] == "/nodes/pve1/qemu/"
    assert payload["ide2"] == "local:iso/debian.iso,media=cdrom"
    assert payload["scsi0"] == "local-lvm:32,iothread=on"
    assert payload["ostype"] == "l26"
    assert payload["cores"] == 2
    assert payload["memory"] == 2048


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("vmid", "", "vmid"),
        ("network_bridge", "", "network_bridge"),
        ("vmcpus", 0, "vmcpus"),
        ("vmmemory", 0, "vmmemory"),
    ],
)
def test_create_reports_missing_required_fields(settings, field, value, expected):
    setattr(settings, field, value)
    manager, client = build(settings)

    with pytest.raises(ProxmoxError, match=f"Missing required fields: {expected}"):
        manager.create()
    assert client.calls == []


def test_create_needs_a_vm_name(settings):
    settings.vm_name = ""
    settings.vm_internal_name = ""
    manager, _ = build(settings)

    with pytest.raises(ProxmoxError, match="vm_internal_name"):
        manager.create()


def test_create_rejects_names_proxmox_would_refuse(settings):
    settings.vm_name = "vm_with_underscore"
    manager, _ = build(settings)

    with pytest.raises(ProxmoxError, match="Invalid VM name"):
        manager.create()


@pytest.mark.parametrize(
    ("template_type", "field", "expected"),
    [("ISO", "iso_path", "iso_path"), ("TEMPLATE", "template_id", "template_id")],
)
def test_create_reports_missing_source_fields(settings, template_type, field, expected):
    settings.template_type = template_type
    setattr(settings, field, "")
    manager, client = build(settings)

    with pytest.raises(
        ProxmoxError, match=f"Missing required field in JSON: {expected}"
    ):
        manager.create()
    assert client.calls == []


def test_create_from_an_iso_needs_a_disk_size(settings):
    settings.template_type = "ISO"
    settings.iso_path = "local:iso/debian.iso"
    settings.disk_size_gb = ""
    manager, client = build(settings)

    with pytest.raises(
        ProxmoxError, match="Missing required field in JSON: disk_size_gb"
    ):
        manager.create()
    assert client.calls == []


def test_create_removes_the_vm_when_a_later_step_fails(settings):
    manager, client = build(settings, errors={"/status/start": ProxmoxError("no boot")})

    with pytest.raises(ProxmoxError, match="no boot"):
        manager.create()

    assert ("DELETE", "/nodes/pve1/qemu/101", None) in client.calls


def test_create_wraps_unexpected_failures(settings):
    manager, _ = build(settings, errors={"/clone": ValueError("boom")})

    with pytest.raises(ProxmoxError, match="boom"):
        manager.create()


def test_cleanup_failures_do_not_mask_the_original_error(settings):
    manager, _ = build(
        settings,
        errors={"/status/start": ProxmoxError("no boot"), "": ProxmoxError("no boot")},
    )

    with pytest.raises(ProxmoxError, match="no boot"):
        manager.create()


# -- power state ---------------------------------------------------------


def test_start_waits_for_the_task(settings):
    manager, client = build(settings)

    assert manager.start() == {"status": "success", "message": "Instance started"}
    assert client.waited == [("POST", "/nodes/pve1/qemu/101/status/start", None)]


def test_reboot_waits_for_the_task(settings):
    manager, client = build(settings)

    assert manager.reboot() == {"status": "success", "message": "Instance rebooted"}
    assert client.waited == [("POST", "/nodes/pve1/qemu/101/status/reboot", None)]


def test_stop_stops_an_existing_vm(settings):
    manager, client = build(settings, responses={"/status/current": {"data": {}}})

    assert manager.stop() == {"status": "success", "message": "Instance stopped"}
    assert ("POST", "/nodes/pve1/qemu/101/status/stop", None) in client.calls


def test_stop_is_idempotent_when_the_vm_is_gone(settings):
    manager, client = build(
        settings, errors={"/status/current": ProxmoxError("not found")}
    )

    assert manager.stop() == {"status": "success", "message": "Instance stopped"}
    assert client.waited == []


def test_delete_is_idempotent_when_the_vm_is_gone(settings):
    manager, client = build(
        settings, errors={"/status/current": ProxmoxError("not found")}
    )

    assert manager.delete() == {"status": "success", "message": "Instance deleted"}
    assert client.waited == []


def test_delete_removes_an_existing_vm(settings):
    manager, client = build(settings, responses={"/status/current": {"data": {}}})

    assert manager.delete() == {"status": "success", "message": "Instance deleted"}
    assert ("DELETE", "/nodes/pve1/qemu/101", None) in client.waited


def test_an_unrelated_error_does_not_count_as_a_missing_vm(settings):
    manager, client = build(
        settings, errors={"/status/current": ProxmoxError("denied")}
    )

    manager.delete()

    # The presence check only short circuits on "not found", never on other errors.
    assert ("DELETE", "/nodes/pve1/qemu/101", None) in client.waited


@pytest.mark.parametrize(
    ("proxmox_status", "power_state"),
    [
        ("running", "poweron"),
        ("stopped", "poweroff"),
        ("paused", "unknown"),
        ("", "unknown"),
    ],
)
def test_status_maps_proxmox_states(settings, proxmox_status, power_state):
    manager, _ = build(
        settings, responses={"/status/current": {"data": {"status": proxmox_status}}}
    )

    assert manager.status() == {"status": "success", "power_state": power_state}


def test_statuses_keys_by_name_and_skips_templates(settings):
    manager, _ = build(
        settings,
        responses={
            "/nodes/pve1/qemu": {
                "data": [
                    {"name": "i-2-3-VM", "status": "running"},
                    {"name": "i-2-4-VM", "status": "stopped"},
                    {"name": "tmpl", "status": "stopped", "template": 1},
                    {"vmid": 105, "status": "suspended"},
                ]
            }
        },
    )

    assert manager.statuses() == {
        "status": "success",
        "power_state": {
            "i-2-3-VM": "poweron",
            "i-2-4-VM": "poweroff",
            "105": "unknown",
        },
    }


def test_statuses_tolerates_an_empty_node(settings):
    manager, _ = build(settings, responses={"/nodes/pve1/qemu": {"data": None}})

    assert manager.statuses() == {"status": "success", "power_state": {}}


def test_statuses_reports_an_unparseable_response(settings):
    manager, _ = build(settings, responses={"/nodes/pve1/qemu": {"data": "garbage"}})

    with pytest.raises(ProxmoxError, match="Failed to parse VM status output"):
        manager.statuses()


# -- console -------------------------------------------------------------


def test_get_console_returns_a_one_time_vnc_ticket(settings):
    manager, _ = build(
        settings,
        responses={
            "/vncproxy": {"data": {"port": "5900", "ticket": "PVEVNC:secret"}},
            "/network": {
                "data": [
                    {"type": "bridge", "method": "static", "address": "10.0.0.1"},
                    {"type": "eth", "method": "static", "address": "192.0.2.10"},
                ]
            },
        },
    )

    assert manager.get_console() == {
        "status": "success",
        "message": "Console retrieved",
        "console": {
            "host": "192.0.2.10",
            "port": "5900",
            "password": "PVEVNC:secret",
            "passwordonetimeuseonly": True,
            "protocol": "vnc",
        },
    }


def test_get_console_needs_a_port_and_ticket(settings):
    manager, _ = build(settings, responses={"/vncproxy": {"data": {"port": "5900"}}})

    with pytest.raises(ProxmoxError, match="missing port/ticket"):
        manager.get_console()


def test_get_console_needs_a_reachable_node_address(settings):
    manager, _ = build(
        settings,
        responses={
            "/vncproxy": {"data": {"port": "5900", "ticket": "t"}},
            "/network": {"data": []},
        },
    )

    with pytest.raises(ProxmoxError, match="Could not determine host IP"):
        manager.get_console()


def test_node_host_falls_back_to_a_bridge_address(settings):
    manager, _ = build(
        settings,
        responses={"/network": {"data": [{"type": "bridge", "cidr": "10.0.0.1/24"}]}},
    )

    assert manager.get_node_host() == "10.0.0.1"


def test_node_host_prefers_a_static_physical_interface(settings):
    manager, _ = build(
        settings,
        responses={
            "/network": {
                "data": [
                    {"type": "eth", "method": "manual", "address": "198.51.100.1"},
                    {"type": "eth", "method": "static", "cidr": "192.0.2.10/24"},
                ]
            }
        },
    )

    assert manager.get_node_host() == "192.0.2.10"


def test_node_host_is_empty_when_the_network_cannot_be_read(settings):
    manager, _ = build(settings, errors={"/network": ProxmoxError("denied")})

    assert manager.get_node_host() == ""


def test_node_host_is_empty_for_an_unparseable_response(settings):
    manager, _ = build(settings, responses={"/network": {"data": "garbage"}})

    assert manager.get_node_host() == ""


# -- snapshots -----------------------------------------------------------


def test_list_snapshots_formats_each_entry(settings):
    manager, _ = build(
        settings,
        responses={
            "/snapshot": {
                "data": [
                    {
                        "name": "before-upgrade",
                        "snaptime": 1_700_000_000,
                        "description": "pre upgrade",
                        "parent": "current",
                        "vmstate": 1,
                    },
                    {"name": "current"},
                ]
            }
        },
    )

    result = manager.list_snapshots()

    assert result["printmessage"] == "true"
    assert result["message"][0]["name"] == "before-upgrade"
    assert result["message"][0]["snaptime"] != "-"
    assert result["message"][1] == {
        "name": "current",
        "snaptime": "-",
        "description": None,
        "parent": "-",
        "vmstate": "-",
    }


def test_list_snapshots_reports_an_unparseable_response(settings):
    manager, _ = build(settings, responses={"/snapshot": {"data": "garbage"}})

    with pytest.raises(ProxmoxError, match="Failed to parse snapshot output"):
        manager.list_snapshots()


def test_create_snapshot_sends_the_name_and_description(settings):
    settings.snap_description = "pre upgrade"
    settings.snap_save_memory = True
    manager, client = build(settings)

    assert manager.create_snapshot() == {
        "status": "success",
        "message": "Instance Snapshot created",
    }
    assert client.calls[0] == (
        "POST",
        "/nodes/pve1/qemu/101/snapshot",
        {"snapname": "before-upgrade", "vmstate": 1, "description": "pre upgrade"},
    )


def test_create_snapshot_omits_an_empty_description(settings):
    manager, client = build(settings)

    manager.create_snapshot()

    assert client.calls[0][2] == {"snapname": "before-upgrade", "vmstate": 0}


def test_restore_snapshot_starts_a_vm_left_stopped_by_the_rollback(settings):
    manager, client = build(
        settings, responses={"/status/current": {"data": {"status": "stopped"}}}
    )

    assert manager.restore_snapshot() == {
        "status": "success",
        "message": "Instance Snapshot restored",
    }
    assert client.calls[0][1] == "/nodes/pve1/qemu/101/snapshot/before-upgrade/rollback"
    assert ("POST", "/nodes/pve1/qemu/101/status/start", None) in client.calls


def test_restore_snapshot_leaves_a_running_vm_alone(settings):
    manager, client = build(
        settings, responses={"/status/current": {"data": {"status": "running"}}}
    )

    manager.restore_snapshot()

    assert "/nodes/pve1/qemu/101/status/start" not in client.paths()


def test_restore_snapshot_ignores_a_failing_status_check(settings):
    manager, _ = build(settings, errors={"/status/current": ProxmoxError("denied")})

    assert manager.restore_snapshot()["message"] == "Instance Snapshot restored"


def test_delete_snapshot_removes_it(settings):
    manager, client = build(settings)

    assert manager.delete_snapshot() == {
        "status": "success",
        "message": "Instance Snapshot deleted",
    }
    assert client.waited == [
        ("DELETE", "/nodes/pve1/qemu/101/snapshot/before-upgrade", None)
    ]


@pytest.mark.parametrize(
    "operation", ["create_snapshot", "restore_snapshot", "delete_snapshot"]
)
def test_snapshot_operations_need_a_name(settings, operation):
    settings.snap_name = ""
    manager, _ = build(settings)

    with pytest.raises(ProxmoxError, match="Missing required field in JSON: snap_name"):
        getattr(manager, operation)()


@pytest.mark.parametrize(
    "operation", ["create_snapshot", "restore_snapshot", "delete_snapshot"]
)
def test_snapshot_operations_reject_invalid_names(settings, operation):
    settings.snap_name = "snap name!"
    manager, _ = build(settings)

    with pytest.raises(ProxmoxError, match="Invalid Snapshot name"):
        getattr(manager, operation)()


def test_from_config_file_builds_a_real_client(config_file):
    manager = ProxmoxManager.from_config_file(config_file, wait_time=42)

    assert manager.settings.node == "pve1"
    assert manager.client.wait_time == 42
