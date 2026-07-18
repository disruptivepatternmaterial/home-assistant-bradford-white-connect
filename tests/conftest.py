"""Pytest setup: keep the unit tests self-contained.

The integration's package ``__init__`` imports the full Home Assistant +
upstream-client stack at import time, which would force every test run
to install the entire HA dev environment. These tests deliberately only
exercise the pure-function modules (``fault_codes``, ``helper``,
``client_compat``), so we add the integration directory directly to
``sys.path`` and import them as flat modules. We also install a minimal
stub for the ``bradford_white_connect_client`` submodules they import, so
the tests run with nothing more than ``pytest`` installed.

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

import dataclasses
import sys
import types
from pathlib import Path
from typing import List, Optional


def _install_upstream_client_stub() -> None:
    # Prefer the real client whenever its public surface is importable
    # (e.g. in CI). A half-installed / namespace-only package must not
    # suppress the stub — ``client_compat`` needs Device/Property/Client.
    try:
        from bradford_white_connect_client import (  # noqa: F401
            BradfordWhiteConnectClient,
        )
        from bradford_white_connect_client.types import (  # noqa: F401
            Device,
            Property,
            PropertyWrapper,
        )

        return
    except ImportError:
        pass

    root = types.ModuleType("bradford_white_connect_client")

    types_mod = types.ModuleType("bradford_white_connect_client.types")

    @dataclasses.dataclass
    class _Device:
        product_name: str = ""
        model: str = ""
        dsn: str = ""
        oem_model: str = ""
        sw_version: str = ""
        template_id: int = 0
        mac: str = ""
        unique_hardware_id: Optional[str] = None
        lan_ip: str = ""
        connected_at: str = ""
        key: int = 0
        lan_enabled: bool = False
        connection_priority: List[str] = dataclasses.field(default_factory=list)
        has_properties: bool = False
        product_class: Optional[str] = None
        connection_status: str = ""
        lat: str = ""
        lng: str = ""
        locality: Optional[str] = None
        device_type: str = ""
        dealer: Optional[str] = None
        facility_uuid: Optional[str] = None
        properties: Optional[dict] = None

    @dataclasses.dataclass
    class _Property:
        type: str = ""
        name: str = ""
        base_type: str = ""
        read_only: bool = False
        direction: str = ""
        scope: str = ""
        data_updated_at: str = ""
        key: int = 0
        device_key: int = 0
        product_name: str = ""
        track_only_changes: bool = False
        display_name: str = ""
        host_sw_version: bool = False
        time_series: bool = False
        derived: bool = False
        app_type: Optional[str] = None
        recipe: Optional[str] = None
        value: Optional[str] = None
        generated_from: Optional[str] = None
        generated_at: Optional[int] = None
        denied_roles: List[str] = dataclasses.field(default_factory=list)
        ack_enabled: bool = False
        retention_days: Optional[int] = None
        ack_status: Optional[str] = None
        ack_message: Optional[str] = None
        acked_at: Optional[str] = None

    @dataclasses.dataclass
    class _PropertyWrapper:
        property: _Property

    types_mod.Device = _Device
    types_mod.Property = _Property
    types_mod.PropertyWrapper = _PropertyWrapper
    root.types = types_mod

    class _BradfordWhiteConnectClient:
        def generate_headers(self, *args, **kwargs):
            return {}

        async def http_get_request(self, url, headers=None):
            return []

        async def get_devices(self):
            return []

        async def get_device_properties(self, device):
            return []

    root.BradfordWhiteConnectClient = _BradfordWhiteConnectClient

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
