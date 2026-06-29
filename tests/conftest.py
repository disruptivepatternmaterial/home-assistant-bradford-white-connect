"""Pytest setup: keep the unit tests self-contained.

The integration's package ``__init__`` imports the full Home Assistant +
upstream-client stack at import time, which would force every test run
to install the entire HA dev environment. These tests deliberately only
exercise the pure-function modules (``fault_codes``, ``helper``), so we
add the integration directory directly to ``sys.path`` and import them
as flat modules. We also install a minimal stub for the
``bradford_white_connect_client`` submodules they import, so the tests
run with nothing more than ``pytest`` installed.

The stub is installed **only when the real client is not importable**. In
CI (``pipenv install --dev`` provides the real client) the real package is
used, so the suite exercises the actual upstream contract — enum values,
``Device`` / ``Property`` shape, ``is_valid`` — and would catch drift. The
stub's enum values mirror the real
``bradford_white_connect_client.constants.BradfordWhiteConnectHeatingModes``
(``HYBRID = 0`` ... ``VACATION = 4``) so a stub-only run can't pass against
fictitious integers.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path


def _install_upstream_client_stub() -> None:
    # Prefer the real client whenever it is importable (e.g. in CI) so the
    # tests run against the genuine upstream contract rather than a stand-in.
    try:
        import bradford_white_connect_client  # noqa: F401

        return
    except ImportError:
        pass

    root = types.ModuleType("bradford_white_connect_client")

    types_mod = types.ModuleType("bradford_white_connect_client.types")

    class _Device:
        """Minimal stand-in for the real Device dataclass."""

        properties: dict | None = None

    types_mod.Device = _Device
    root.types = types_mod

    constants_mod = types.ModuleType("bradford_white_connect_client.constants")

    class _BradfordWhiteConnectHeatingModes:
        # Must mirror the real upstream enum (constants.py): 0-based.
        HYBRID = 0
        ELECTRIC = 1
        HEAT_PUMP = 2
        HYBRID_PLUS = 3
        VACATION = 4

        @staticmethod
        def is_valid(value: int) -> bool:
            return value in (0, 1, 2, 3, 4)

    constants_mod.BradfordWhiteConnectHeatingModes = _BradfordWhiteConnectHeatingModes
    root.constants = constants_mod

    sys.modules["bradford_white_connect_client"] = root
    sys.modules["bradford_white_connect_client.types"] = types_mod
    sys.modules["bradford_white_connect_client.constants"] = constants_mod


_install_upstream_client_stub()


_INTEGRATION_DIR = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "bradford_white_connect"
)
if str(_INTEGRATION_DIR) not in sys.path:
    sys.path.insert(0, str(_INTEGRATION_DIR))
