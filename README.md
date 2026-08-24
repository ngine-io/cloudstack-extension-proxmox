# CloudStack Proxmox VE Extension

[![Tests](https://github.com/ngine-io/cloudstack-extension-proxmox/actions/workflows/test.yml/badge.svg)](https://github.com/ngine-io/cloudstack-extension-proxmox/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/cloudstack-extension-proxmox-ngine.svg)](https://pypi.org/project/cloudstack-extension-proxmox-ngine/)
[![Python versions](https://img.shields.io/pypi/pyversions/cloudstack-extension-proxmox-ngine.svg)](https://pypi.org/project/cloudstack-extension-proxmox-ngine/)

An [Apache CloudStack](https://cloudstack.apache.org/) *Orchestrator* extension that
manages virtual machines on [Proxmox VE](https://www.proxmox.com/en/proxmox-virtual-environment).

CloudStack invokes the extension as a command line program, passing an action and the
path to a JSON payload; the extension talks to the Proxmox API and writes a single JSON
document to stdout. Everything is implemented on top of the Python standard library, so
the extension has **no runtime dependencies** and runs with the management server's
system interpreter.

## Installation

```bash
pip install cloudstack-extension-proxmox-ngine
```

This provides the `cloudstack-extension-proxmox` command. CloudStack expects to find an
executable inside the extension directory, so link the command into place:

```bash
mkdir -p /usr/share/cloudstack-management/extensions/Proxmox-Ngine
ln -s "$(command -v cloudstack-extension-proxmox)" \
      /usr/share/cloudstack-management/extensions/Proxmox-Ngine/proxmox.sh
```

Register the extension in CloudStack (`Extensions` → `Add Extension`, type
`Orchestrator`) and add the Proxmox connection details as extension or host details.

## Usage

```bash
cloudstack-extension-proxmox <action> <payload.json> [timeout-seconds]
```

| Action | Description |
| --- | --- |
| `prepare` | Reserve the next free VM ID and return it as `proxmox_vmid` |
| `create` | Clone a template or install from an ISO, attach the NICs and start the VM |
| `start`, `stop`, `reboot`, `delete` | Power and lifecycle operations |
| `status`, `statuses` | Power state of one VM, or of every VM on the node |
| `getconsole` | Issue a one time VNC ticket for the console proxy |
| `listsnapshots`, `createsnapshot`, `restoresnapshot`, `deletesnapshot` | Snapshot management |

`stop` and `delete` are idempotent: a VM that no longer exists is reported as success.

### Payload

The payload is written by CloudStack. The fields the extension reads are:

| Path | Meaning |
| --- | --- |
| `externaldetails.host.url` / `.extension.url` | Proxmox API base URL (host wins) |
| `externaldetails.host.user`, `.token`, `.secret` | API token credentials |
| `externaldetails.host.node` | Proxmox node name |
| `externaldetails.host.network_bridge` | Bridge the VM NICs attach to |
| `externaldetails.host.verify_tls_certificate` | Verify the API certificate (default `true`) |
| `externaldetails.virtualmachine.template_type` | `ISO` or anything else for a template clone |
| `externaldetails.virtualmachine.template_id` | Template VM ID to clone |
| `externaldetails.virtualmachine.iso_path`, `.iso_os_type`, `.disk_size_gb` | ISO installation |
| `externaldetails.virtualmachine.storage`, `.is_full_clone` | Storage and clone mode |
| `cloudstack.vm.details` | VM name, CPU, memory and NICs from the service offering |
| `parameters.snap_name`, `.snap_description`, `.snap_save_memory` | Snapshot action inputs |

### As a library

```python
from cloudstack_extension_proxmox_ngine import ProxmoxManager

manager = ProxmoxManager.from_config_file("payload.json")
print(manager.status())
# {'status': 'success', 'power_state': 'poweron'}
```

Operations return the CloudStack result document and raise `ProxmoxError` on failure.

## Development

The project uses [uv](https://docs.astral.sh/uv/):

```bash
uv sync --group dev
uv run pytest              # tests with coverage
uv run black --check .     # formatting
uv run ruff check .        # linting
uv run mypy                # type checking
```

Pull requests run the same checks on Python 3.10 through 3.13.

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
