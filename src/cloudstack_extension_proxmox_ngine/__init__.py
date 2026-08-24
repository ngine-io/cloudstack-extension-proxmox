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


"""Proxmox VE extension for Apache CloudStack.

The package exposes the extension as a library so the Proxmox operations can be
imported and tested, while :mod:`cloudstack_extension_proxmox_ngine.cli`
provides the JSON-on-stdout contract CloudStack itself uses.
"""

from __future__ import annotations

from .client import ProxmoxClient
from .errors import ProxmoxError
from .manager import ProxmoxManager
from .settings import ProxmoxSettings, load_settings, parse_settings

__version__ = "0.1.0"

__all__ = [
    "ProxmoxClient",
    "ProxmoxError",
    "ProxmoxManager",
    "ProxmoxSettings",
    "__version__",
    "load_settings",
    "parse_settings",
]
