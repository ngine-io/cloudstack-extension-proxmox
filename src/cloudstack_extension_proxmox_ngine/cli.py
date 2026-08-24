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


"""Command line entry point invoked by the CloudStack management server.

CloudStack calls the extension as ``<script> <action> <payload.json> [timeout]``
and reads a single JSON document from stdout.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from typing import Any, NoReturn

from .client import DEFAULT_WAIT_SECONDS
from .coerce import as_int
from .errors import ProxmoxError
from .manager import ProxmoxManager
from .output import fail, succeed

USAGE = "Usage: proxmox.py <operation> '<json-file-path>'"


def operations(manager: ProxmoxManager) -> dict[str, Callable[[], dict[str, Any]]]:
    """Map the action names CloudStack uses onto manager methods."""
    return {
        "prepare": manager.prepare,
        "create": manager.create,
        "start": manager.start,
        "stop": manager.stop,
        "reboot": manager.reboot,
        "delete": manager.delete,
        "status": manager.status,
        "statuses": manager.statuses,
        "getconsole": manager.get_console,
        "listsnapshots": manager.list_snapshots,
        "createsnapshot": manager.create_snapshot,
        "restoresnapshot": manager.restore_snapshot,
        "deletesnapshot": manager.delete_snapshot,
    }


def main(argv: Sequence[str] | None = None) -> NoReturn:
    """Run one extension action and print its JSON result."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2:
        fail(USAGE)

    action = args[0].lower()
    config_path = args[1]
    wait_time = (
        as_int(args[2], DEFAULT_WAIT_SECONDS) if len(args) > 2 else DEFAULT_WAIT_SECONDS
    )

    try:
        manager = ProxmoxManager.from_config_file(config_path, wait_time=wait_time)
        operation = operations(manager).get(action)
        if operation is None:
            fail("Invalid action")
        result = operation()
    except ProxmoxError as exc:
        fail(str(exc))
    except SystemExit:
        raise
    except Exception as exc:  # CloudStack only understands the JSON contract.
        fail(str(exc))
    succeed(result)


if __name__ == "__main__":
    main()
