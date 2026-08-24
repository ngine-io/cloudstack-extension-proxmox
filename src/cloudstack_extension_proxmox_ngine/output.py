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

"""CloudStack talks to an extension over stdout: one JSON document, then exit.

Both helpers terminate the process, which is why they are annotated ``NoReturn``.
"""

from __future__ import annotations

import json
from typing import Any, NoReturn


def fail(message: str) -> NoReturn:
    """Print an error document and exit with a non-zero status."""
    print(json.dumps({"status": "error", "error": message}))
    raise SystemExit(1)


def succeed(data: dict[str, Any]) -> NoReturn:
    """Print a result document and exit successfully."""
    print(json.dumps(data))
    raise SystemExit(0)
