from __future__ import annotations

import json

import pytest

from cloudstack_extension_proxmox_ngine import cli
from cloudstack_extension_proxmox_ngine.client import DEFAULT_WAIT_SECONDS
from cloudstack_extension_proxmox_ngine.errors import ProxmoxError


def run(capsys, argv):
    """Run the CLI and return its exit code together with the JSON it printed."""
    with pytest.raises(SystemExit) as excinfo:
        cli.main(argv)
    return excinfo.value.code, json.loads(capsys.readouterr().out)


def test_every_cloudstack_action_is_wired_up(manager):
    assert set(cli.operations(manager)) == {
        "prepare",
        "create",
        "start",
        "stop",
        "reboot",
        "delete",
        "status",
        "statuses",
        "getconsole",
        "listsnapshots",
        "createsnapshot",
        "restoresnapshot",
        "deletesnapshot",
    }


def test_a_successful_action_prints_its_result_and_exits_zero(
    capsys, config_file, monkeypatch
):
    monkeypatch.setattr(
        cli.ProxmoxManager,
        "prepare",
        lambda self: {"details": {"proxmox_vmid": "102"}},
    )

    code, output = run(capsys, ["prepare", str(config_file)])

    assert code == 0
    assert output == {"details": {"proxmox_vmid": "102"}}


def test_the_action_name_is_case_insensitive(capsys, config_file, monkeypatch):
    monkeypatch.setattr(cli.ProxmoxManager, "start", lambda self: {"status": "success"})

    code, _ = run(capsys, ["START", str(config_file)])

    assert code == 0


def test_the_wait_time_argument_reaches_the_client(config_file, monkeypatch):
    captured = {}

    def record(cls, path, wait_time=None):
        captured["wait_time"] = wait_time
        raise ProxmoxError("stop here")

    monkeypatch.setattr(cli.ProxmoxManager, "from_config_file", classmethod(record))

    with pytest.raises(SystemExit):
        cli.main(["status", str(config_file), "45"])
    assert captured["wait_time"] == 45


def test_an_unparseable_wait_time_falls_back_to_the_default(config_file, monkeypatch):
    captured = {}

    def record(cls, path, wait_time=None):
        captured["wait_time"] = wait_time
        raise ProxmoxError("stop here")

    monkeypatch.setattr(cli.ProxmoxManager, "from_config_file", classmethod(record))

    with pytest.raises(SystemExit):
        cli.main(["status", str(config_file), "soon"])
    assert captured["wait_time"] == DEFAULT_WAIT_SECONDS


def test_too_few_arguments_print_the_usage(capsys):
    code, output = run(capsys, ["status"])

    assert code == 1
    assert output == {"status": "error", "error": cli.USAGE}


def test_an_unknown_action_is_rejected(capsys, config_file):
    code, output = run(capsys, ["explode", str(config_file)])

    assert code == 1
    assert output == {"status": "error", "error": "Invalid action"}


def test_a_missing_config_file_is_reported_as_json(capsys, tmp_path):
    code, output = run(capsys, ["status", str(tmp_path / "nope.json")])

    assert code == 1
    assert output["status"] == "error"
    assert "JSON file not found" in output["error"]


def test_proxmox_errors_are_reported_as_json(capsys, config_file, monkeypatch):
    def explode(self):
        raise ProxmoxError("VM 101 not found")

    monkeypatch.setattr(cli.ProxmoxManager, "status", explode)

    code, output = run(capsys, ["status", str(config_file)])

    assert code == 1
    assert output == {"status": "error", "error": "VM 101 not found"}


def test_unexpected_errors_are_reported_as_json(capsys, config_file, monkeypatch):
    def explode(self):
        raise ValueError("something odd")

    monkeypatch.setattr(cli.ProxmoxManager, "status", explode)

    code, output = run(capsys, ["status", str(config_file)])

    assert code == 1
    assert output == {"status": "error", "error": "something odd"}


def test_arguments_default_to_sys_argv(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["proxmox.py", "status"])

    code, output = run(capsys, None)

    assert code == 1
    assert output["error"] == cli.USAGE
