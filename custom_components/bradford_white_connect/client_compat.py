"""Forward-compatible shims for bradford-white-connect-client vs live Ayla API.

Ayla's device/property JSON regularly gains fields the pinned client does not
model. Upstream constructs with ``Model(**payload)``, which raises
``TypeError`` on unknown kwargs and takes the whole integration down.

This module monkey-patches the two unpack sites (``get_devices``,
``get_device_properties``) to keep only fields declared on the dataclass.
New Ayla keys are ignored (and logged once); when upstream adds a field to
its model, filtering stops automatically via ``dataclasses.fields``.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, TypeVar

from bradford_white_connect_client import BradfordWhiteConnectClient
from bradford_white_connect_client.types import Device, Property, PropertyWrapper

_LOGGER = logging.getLogger(__name__)
_PATCHED = False
_DEVICE_FIELDS = {f.name for f in dataclasses.fields(Device)}
_PROPERTY_FIELDS = {f.name for f in dataclasses.fields(Property)}
_LOGGED_UNKNOWN: set[tuple[str, tuple[str, ...]]] = set()

_T = TypeVar("_T")


def filter_known_fields(
    raw: dict[str, Any], known: set[str], label: str
) -> dict[str, Any]:
    """Return ``raw`` restricted to ``known`` keys; log novel keys once."""
    unknown = tuple(sorted(set(raw) - known))
    if unknown and (label, unknown) not in _LOGGED_UNKNOWN:
        _LOGGED_UNKNOWN.add((label, unknown))
        # #region agent log
        _LOGGER.warning("Ignoring unsupported Ayla %s fields: %s", label, list(unknown))
        # #endregion
    return {k: v for k, v in raw.items() if k in known}


def instantiate_from_payload(
    model: type[_T], raw: dict[str, Any], label: str
) -> _T:
    """Build a dataclass instance, ignoring keys the model does not declare."""
    known = {f.name for f in dataclasses.fields(model)}  # type: ignore[arg-type]
    return model(**filter_known_fields(raw, known, label))


def apply_client_compat_patches() -> None:
    """Monkey-patch client methods that break on newer Ayla payloads."""
    global _PATCHED
    if _PATCHED:
        return

    async def get_devices_compat(self: BradfordWhiteConnectClient) -> list[Device]:
        headers = self.generate_headers()
        url = "https://ads-field.aylanetworks.com/apiv1/devices.json"
        response_json = await self.http_get_request(url, headers=headers)
        return [
            instantiate_from_payload(Device, item["device"], "device")
            for item in response_json
        ]

    async def get_device_properties_compat(
        self: BradfordWhiteConnectClient, device: Device
    ) -> list[PropertyWrapper]:
        headers = self.generate_headers()
        url = (
            "https://ads-field.aylanetworks.com"
            f"/apiv1/dsns/{device.dsn}/properties.json"
        )
        response_json = await self.http_get_request(url, headers=headers)
        return [
            PropertyWrapper(
                instantiate_from_payload(
                    Property, item["property"], "property"
                )
            )
            for item in response_json
        ]

    BradfordWhiteConnectClient.get_devices = get_devices_compat  # type: ignore[method-assign]
    BradfordWhiteConnectClient.get_device_properties = (  # type: ignore[method-assign]
        get_device_properties_compat
    )
    _PATCHED = True


def reset_client_compat_patches_for_tests() -> None:
    """Test helper: allow re-applying patches after a prior apply."""
    global _PATCHED
    _PATCHED = False
    _LOGGED_UNKNOWN.clear()
