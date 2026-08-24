from __future__ import annotations

import io
import json
from urllib import error, parse

import pytest

from cloudstack_extension_proxmox_ngine import client as client_module
from cloudstack_extension_proxmox_ngine.client import (
    DEFAULT_WAIT_SECONDS,
    ProxmoxClient,
    extract_error_message,
    is_not_found,
)
from cloudstack_extension_proxmox_ngine.errors import ProxmoxError


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False


@pytest.fixture
def urlopen(monkeypatch):
    """Capture requests and serve queued response bodies."""

    class Recorder:
        def __init__(self):
            self.requests = []
            self.bodies: list[str | Exception] = []

        def __call__(self, req, context=None, timeout=None):
            self.requests.append((req, context, timeout))
            body = self.bodies.pop(0) if self.bodies else "{}"
            if isinstance(body, Exception):
                raise body
            return FakeResponse(body.encode("utf-8"))

    recorder = Recorder()
    monkeypatch.setattr(client_module.request, "urlopen", recorder)
    return recorder


def test_get_request_carries_the_token_and_no_body(settings, urlopen):
    urlopen.bodies = [json.dumps({"data": {"status": "running"}})]

    result = ProxmoxClient(settings).call("get", "/nodes/pve1/qemu/101/status/current")

    assert result == {"data": {"status": "running"}}
    req = urlopen.requests[0][0]
    assert (
        req.full_url
        == "https://pve.example.com/api2/json/nodes/pve1/qemu/101/status/current"
    )
    assert req.get_method() == "GET"
    assert req.headers["Authorization"] == "PVEAPIToken=root@pam!cloudstack=s3cr3t"
    assert req.data is None


def test_mapping_bodies_are_form_encoded(settings, urlopen):
    ProxmoxClient(settings).call("POST", "/nodes/pve1/qemu/", {"vmid": 101, "numa": 0})

    req = urlopen.requests[0][0]
    assert parse.parse_qs(req.data.decode()) == {"vmid": ["101"], "numa": ["0"]}
    assert req.headers["Content-type"] == "application/x-www-form-urlencoded"


def test_string_bodies_are_sent_verbatim(settings, urlopen):
    ProxmoxClient(settings).call("POST", "/nodes/pve1/qemu/", "vmid=101")

    assert urlopen.requests[0][0].data == b"vmid=101"


def test_an_empty_body_becomes_an_empty_mapping(settings, urlopen):
    urlopen.bodies = ["   "]
    assert ProxmoxClient(settings).call("GET", "/cluster/nextid") == {}


def test_a_non_json_body_is_reported(settings, urlopen):
    urlopen.bodies = ["<html>gateway</html>"]
    with pytest.raises(ProxmoxError, match="Invalid JSON response"):
        ProxmoxClient(settings).call("GET", "/cluster/nextid")


def test_a_json_array_body_is_rejected(settings, urlopen):
    urlopen.bodies = ["[1, 2]"]
    with pytest.raises(ProxmoxError, match="Invalid response from Proxmox API"):
        ProxmoxClient(settings).call("GET", "/cluster/nextid")


def test_http_errors_surface_the_proxmox_message(settings, urlopen):
    body = io.BytesIO(json.dumps({"message": "VM 101 not found"}).encode())
    urlopen.bodies = [error.HTTPError("url", 500, "Internal Error", {}, body)]

    with pytest.raises(ProxmoxError, match="VM 101 not found"):
        ProxmoxClient(settings).call("GET", "/nodes/pve1/qemu/101/status/current")


def test_connection_errors_surface_the_reason(settings, urlopen):
    urlopen.bodies = [error.URLError("connection refused")]

    with pytest.raises(ProxmoxError, match="connection refused"):
        ProxmoxClient(settings).call("GET", "/cluster/nextid")


def test_tls_verification_is_disabled_only_when_configured(settings, urlopen):
    ProxmoxClient(settings).call("GET", "/cluster/nextid")
    assert urlopen.requests[0][1].verify_mode.name == "CERT_NONE"

    settings.verify_tls_certificate = True
    ProxmoxClient(settings).call("GET", "/cluster/nextid")
    assert urlopen.requests[1][1].verify_mode.name == "CERT_REQUIRED"


def test_wait_time_falls_back_to_the_default(settings):
    assert ProxmoxClient(settings, wait_time=0).wait_time == DEFAULT_WAIT_SECONDS
    assert ProxmoxClient(settings, wait_time=-1).wait_time == DEFAULT_WAIT_SECONDS
    assert ProxmoxClient(settings, wait_time=30).wait_time == 30


def test_call_and_wait_polls_the_returned_task(settings, urlopen, monkeypatch):
    monkeypatch.setattr(client_module.time, "sleep", lambda _: None)
    upid = "UPID:pve1:0001:qmstart:101:root@pam:"
    urlopen.bodies = [
        json.dumps({"data": upid}),
        json.dumps({"data": {"status": "running"}}),
        json.dumps({"data": {"status": "stopped", "exitstatus": "OK"}}),
    ]

    ProxmoxClient(settings).call_and_wait("POST", "/nodes/pve1/qemu/101/status/start")

    assert len(urlopen.requests) == 3
    assert parse.quote(upid, safe="") in urlopen.requests[1][0].full_url


def test_call_and_wait_reports_a_missing_upid(settings, urlopen):
    urlopen.bodies = [json.dumps({"error": "no permission"})]

    with pytest.raises(ProxmoxError, match="no permission"):
        ProxmoxClient(settings).call_and_wait(
            "POST", "/nodes/pve1/qemu/101/status/start"
        )


def test_a_failed_task_raises_with_its_exit_status(settings, urlopen):
    urlopen.bodies = [json.dumps({"data": {"status": "stopped", "exitstatus": "boom"}})]

    with pytest.raises(ProxmoxError, match="Task failed with exit status: boom"):
        ProxmoxClient(settings).wait_for_task("UPID:pve1:0001:")


def test_waiting_times_out(settings, urlopen, monkeypatch):
    clock = iter([0.0, 10.0, 100.0])
    monkeypatch.setattr(client_module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(client_module.time, "sleep", lambda _: None)
    urlopen.bodies = [json.dumps({"data": {"status": "running"}})]

    with pytest.raises(ProxmoxError, match="Timeout while waiting"):
        ProxmoxClient(settings, wait_time=5).wait_for_task("UPID:pve1:0001:")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"message": "boom"}', "boom"),
        ('{"error": "denied"}', "denied"),
        ('{"errors": {"vmid": "invalid"}}', "invalid"),
        ("plain text", "HTTP 500: Server Error: plain text"),
        ("", "HTTP 500: Server Error: Unknown error"),
        ("[1]", "HTTP 500: Server Error: [1]"),
    ],
)
def test_extract_error_message(raw, expected):
    assert expected in extract_error_message(raw, 500, "Server Error")


def test_extract_error_message_without_a_reason():
    assert extract_error_message("", 404, None) == "HTTP 404: Unknown error"


@pytest.mark.parametrize(
    "message",
    [
        "VM 101 not found",
        "Configuration file does not exist",
        "no such VM",
        "unable to find a virtual machine",
    ],
)
def test_is_not_found_recognizes_proxmox_phrasings(message):
    assert is_not_found(ProxmoxError(message)) is True


def test_is_not_found_ignores_unrelated_errors():
    assert is_not_found(ProxmoxError("permission denied")) is False
