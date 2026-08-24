# Changelog

All notable changes to this project are documented in this file. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0]

### Added

- Initial release of the Proxmox VE orchestrator extension for Apache CloudStack,
  packaged as the `cloudstack-extension-proxmox-ngine` library with the
  `cloudstack-extension-proxmox` command line entry point.
- Lifecycle actions (`prepare`, `create`, `start`, `stop`, `reboot`, `delete`), state
  reporting (`status`, `statuses`), console access (`getconsole`) and snapshot
  management (`listsnapshots`, `createsnapshot`, `restoresnapshot`, `deletesnapshot`).
