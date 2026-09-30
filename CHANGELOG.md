# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-09-30

### Added

- Support for Python 3.14.

### Changed

- NICs on networks without a VLAN, or with CloudStack's `vlan://untagged`, are now
  attached to the bridge without a VLAN tag instead of being skipped.

### Fixed

- `create` no longer deletes an existing VM when Proxmox rejects the clone or
  install request, for example because the VM ID is already taken. Cleanup now only
  removes a VM that the failed `create` itself started.
- The `proxmox_vmid` detail is now validated as a number before it is used in API
  requests. An empty ID previously made `stop` and `delete` report success without
  touching any VM.
- The CLI usage message now shows the installed command name and its arguments.
- The source distribution no longer references a non-existent `NOTICE` file.

## [0.1.0] - 2026-08-24

### Added

- Initial release of the Proxmox VE orchestrator extension for Apache CloudStack.
- Actions `prepare`, `create`, `start`, `stop`, `reboot`, `delete`, `status`,
  `statuses` and `getconsole`.
- Snapshot actions `listsnapshots`, `createsnapshot`, `restoresnapshot` and
  `deletesnapshot`.
- VM creation by cloning a template or by installing from an ISO.
- `cloudstack-extension-proxmox` command and an importable library API.

[Unreleased]: https://github.com/ngine-io/cloudstack-extension-proxmox/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/ngine-io/cloudstack-extension-proxmox/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ngine-io/cloudstack-extension-proxmox/releases/tag/v0.1.0
