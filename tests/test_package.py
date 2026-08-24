from __future__ import annotations

import subprocess
import sys

import cloudstack_extension_proxmox_ngine as package


def test_the_public_api_is_importable():
    for name in package.__all__:
        assert hasattr(package, name)


def test_the_version_looks_like_a_release():
    assert package.__version__.count(".") >= 2


def test_the_module_can_be_executed_as_a_script():
    result = subprocess.run(
        [sys.executable, "-m", "cloudstack_extension_proxmox_ngine"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert '"status": "error"' in result.stdout
