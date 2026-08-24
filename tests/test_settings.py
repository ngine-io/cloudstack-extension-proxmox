from __future__ import annotations

import json

import pytest

from cloudstack_extension_proxmox_ngine.errors import ProxmoxError
from cloudstack_extension_proxmox_ngine.settings import (
    load_payload,
    load_settings,
    parse_settings,
)


def test_parses_a_full_payload(payload):
    settings = parse_settings(payload)

    assert settings.url == "https://pve.example.com"
    assert settings.node == "pve1"
    assert settings.network_bridge == "vmbr0"
    assert settings.verify_tls_certificate is False
    assert settings.vm_name == "i-2-3-VM"
    assert settings.vm_internal_name == "i-2-3-VM"
    assert settings.vmid == "101"
    assert settings.vmcpus == 2
    assert settings.vmmemory == 2147483648
    assert settings.is_full_clone is True
    assert settings.snap_name == "before-upgrade"


def test_host_values_win_over_extension_defaults(payload):
    assert parse_settings(payload).url == "https://pve.example.com"


def test_extension_values_are_used_when_the_host_has_none(payload):
    del payload["externaldetails"]["host"]["url"]
    assert parse_settings(payload).url == "https://fallback.example.com"


def test_nics_become_parallel_mac_and_vlan_lists(payload):
    settings = parse_settings(payload)
    assert settings.mac_addresses == ["02:00:00:aa:bb:cc", "02:00:00:aa:bb:dd"]
    assert settings.vlans == ["100", "200"]


def test_malformed_nics_are_ignored(payload):
    payload["cloudstack.vm.details"]["nics"] = "broken"
    settings = parse_settings(payload)
    assert settings.mac_addresses == []
    assert settings.vlans == []


def test_defaults_apply_when_the_virtualmachine_section_is_absent(payload):
    del payload["externaldetails"]["virtualmachine"]
    settings = parse_settings(payload)
    assert settings.storage == "local-lvm"
    assert settings.iso_os_type == "l26"
    assert settings.disk_size_gb == "64"
    assert settings.is_full_clone is False


def test_tls_verification_defaults_to_enabled(payload):
    del payload["externaldetails"]["host"]["verify_tls_certificate"]
    assert parse_settings(payload).verify_tls_certificate is True


@pytest.mark.parametrize("missing", ["url", "user", "token", "secret", "node"])
def test_missing_connection_fields_are_reported(payload, missing):
    payload["externaldetails"]["host"].pop(missing)
    payload["externaldetails"]["extension"] = {}

    with pytest.raises(ProxmoxError, match=f"Missing required fields: {missing}"):
        parse_settings(payload)


def test_all_missing_connection_fields_are_listed_at_once():
    with pytest.raises(ProxmoxError) as excinfo:
        parse_settings({})
    assert "url user token secret node" in str(excinfo.value)


def test_auth_header_uses_the_proxmox_token_format(settings):
    assert settings.auth_header == "PVEAPIToken=root@pam!cloudstack=s3cr3t"


def test_load_payload_reads_the_config_file(config_file, payload):
    assert load_payload(config_file) == payload


def test_load_settings_reads_and_parses(config_file):
    assert load_settings(config_file).node == "pve1"


def test_load_payload_reports_a_missing_file(tmp_path):
    with pytest.raises(ProxmoxError, match="JSON file not found"):
        load_payload(tmp_path / "nope.json")


def test_load_payload_reports_invalid_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ProxmoxError, match="Invalid JSON in file"):
        load_payload(path)


def test_load_payload_rejects_a_non_object_document(tmp_path):
    path = tmp_path / "list.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(ProxmoxError, match="Invalid JSON input"):
        load_payload(path)


def test_load_payload_reports_an_unreadable_path(tmp_path):
    with pytest.raises(ProxmoxError, match="Unable to read JSON file"):
        load_payload(tmp_path)
