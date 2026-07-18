"""Regression tests: Ayla may add device/property fields at any time."""

from __future__ import annotations

import asyncio
import dataclasses
from typing import Any, Optional

import client_compat


@dataclasses.dataclass
class _SampleModel:
    name: str
    value: int
    optional: Optional[str] = None


def test_filter_known_fields_drops_unknown_keys() -> None:
    client_compat.reset_client_compat_patches_for_tests()
    known = {f.name for f in dataclasses.fields(_SampleModel)}
    filtered = client_compat.filter_known_fields(
        {
            "name": "tank",
            "value": 1,
            "optional": "x",
            "oem": "future",
            "transport_type": "wifi",
            "passthrough": True,
        },
        known,
        "sample",
    )
    assert filtered == {"name": "tank", "value": 1, "optional": "x"}


def test_instantiate_from_payload_tolerates_future_keys() -> None:
    client_compat.reset_client_compat_patches_for_tests()
    obj = client_compat.instantiate_from_payload(
        _SampleModel,
        {
            "name": "tank",
            "value": 42,
            "brand_new_ayla_field": {"nested": True},
            "another_new_field": 0,
        },
        "sample",
    )
    assert obj == _SampleModel(name="tank", value=42, optional=None)


def _minimal_device_payload() -> dict[str, Any]:
    return {
        "product_name": "heater",
        "model": "m",
        "dsn": "AC000TEST",
        "oem_model": "om",
        "sw_version": "1",
        "template_id": 1,
        "mac": "aa",
        "unique_hardware_id": None,
        "lan_ip": "1.2.3.4",
        "connected_at": "t",
        "key": 1,
        "lan_enabled": True,
        "connection_priority": ["wifi"],
        "has_properties": True,
        "product_class": None,
        "connection_status": "Online",
        "lat": "0",
        "lng": "0",
        "locality": None,
        "device_type": "Wifi",
        "dealer": None,
        "facility_uuid": None,
    }


def _minimal_property_payload() -> dict[str, Any]:
    return {
        "type": "string",
        "name": "heater_name",
        "base_type": "string",
        "read_only": False,
        "direction": "input",
        "scope": "user",
        "data_updated_at": "t",
        "key": 1,
        "device_key": 1,
        "product_name": "p",
        "track_only_changes": False,
        "display_name": "Heater Name",
        "host_sw_version": False,
        "time_series": False,
        "derived": False,
        "app_type": None,
        "recipe": None,
        "value": "bridge",
        "generated_from": None,
        "generated_at": None,
        "denied_roles": [],
        "ack_enabled": False,
        "retention_days": None,
    }


def test_patched_get_devices_ignores_unknown_device_fields() -> None:
    """Patched get_devices must not TypeError on extra Ayla keys."""
    from bradford_white_connect_client import BradfordWhiteConnectClient

    client_compat.reset_client_compat_patches_for_tests()
    client_compat.apply_client_compat_patches()

    payload = _minimal_device_payload()
    payload.update(
        {
            "oem": "96e7aee3",
            "transport_type": "wifi",
            "totally_new_field_2027": True,
        }
    )

    class _Fake:
        def generate_headers(self, *args: Any, **kwargs: Any) -> dict[str, str]:
            return {}

        async def http_get_request(
            self, url: str, headers: Optional[dict] = None
        ):
            return [{"device": payload}]

    devices = asyncio.run(BradfordWhiteConnectClient.get_devices(_Fake()))
    assert len(devices) == 1
    assert devices[0].dsn == "AC000TEST"


def test_patched_get_device_properties_ignores_passthrough() -> None:
    from bradford_white_connect_client import BradfordWhiteConnectClient
    from bradford_white_connect_client.types import Device

    client_compat.reset_client_compat_patches_for_tests()
    client_compat.apply_client_compat_patches()

    prop = _minimal_property_payload()
    prop.update({"passthrough": False, "future_prop_field": 123})
    device = Device(**_minimal_device_payload())

    class _Fake:
        def generate_headers(self, *args: Any, **kwargs: Any) -> dict[str, str]:
            return {}

        async def http_get_request(
            self, url: str, headers: Optional[dict] = None
        ):
            return [{"property": prop}]

    wrappers = asyncio.run(
        BradfordWhiteConnectClient.get_device_properties(_Fake(), device)
    )
    assert len(wrappers) == 1
    assert wrappers[0].property.name == "heater_name"
