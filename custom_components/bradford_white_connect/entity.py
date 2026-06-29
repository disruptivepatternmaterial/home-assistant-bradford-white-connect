"""The base entity for the Bradford White Connect integration."""

from __future__ import annotations

from typing import TypeVar

from bradford_white_connect_client import BradfordWhiteConnectClient
from bradford_white_connect_client.types import Device
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import (
    BradfordWhiteConnectEnergyCoordinator,
    BradfordWhiteConnectStatusCoordinator,
)

_BradfordWhiteConnectCoordinatorT = TypeVar(
    "_BradfordWhiteConnectCoordinatorT", bound=BradfordWhiteConnectStatusCoordinator
)


class BradfordWhiteConnectEntity(CoordinatorEntity[_BradfordWhiteConnectCoordinatorT]):
    """Base entity for Bradford White Connect."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: _BradfordWhiteConnectCoordinatorT, dsn: str, device: Device
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._dsn = dsn
        self._device = device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dsn)},
        )

    @property
    def client(self) -> BradfordWhiteConnectClient:
        """Shortcut to get the API client."""
        return self.coordinator.client


class BradfordWhiteConnectStatusEntity(
    BradfordWhiteConnectEntity[BradfordWhiteConnectStatusCoordinator]
):
    """Base entity for entities that use data from the status coordinator.

    Availability is gated on two things: the coordinator's most recent
    update succeeded AND this device's DSN is present in the latest
    coordinator data. The second clause matters because the coordinator
    *skips* a device whose telemetry is missing/out of range for a cycle
    (see ``_device_is_valid``); without this gate the entity would report
    ``available`` while every ``self.device`` access raised ``KeyError``.
    The cloud-reported ``device.connection_status`` field is intentionally
    not used as an availability gate because it can report ``Offline`` for
    devices that are reachable; it is exposed as a diagnostic sensor instead.
    """

    @property
    def available(self) -> bool:
        """Return True only when this device is present in the latest update."""
        return super().available and self._dsn in self.coordinator.data

    @property
    def device(self) -> Device:
        """Return the device from the latest coordinator data.

        Falls back to the snapshot captured at setup when this DSN is absent
        from the current update (i.e. the device was skipped this cycle).
        The entity is already reported ``unavailable`` in that case, so the
        fallback only exists to keep state reads and write-service handlers
        from raising ``KeyError`` instead of a clean unavailability/error.
        """
        return self.coordinator.data.get(self._dsn, self._device)


class BradfordWhiteConnectDescribedStatusEntity(BradfordWhiteConnectStatusEntity):
    """Status-coordinator entity driven by an ``EntityDescription``.

    Every per-platform property entity (button/binary_sensor/number/sensor/
    switch/text) follows the same shape: take a description, set it on the
    entity, and derive ``unique_id`` from ``{dsn}_{description.key}``. This
    mixin folds that boilerplate into one place.

    Concrete platform subclasses just declare the ``entity_description``
    type annotation for their description subclass; they no longer need
    to override ``__init__``.
    """

    def __init__(
        self,
        coordinator: BradfordWhiteConnectStatusCoordinator,
        dsn: str,
        device: Device,
        description: EntityDescription,
    ) -> None:
        """Initialize the entity from a shared description."""
        super().__init__(coordinator, dsn, device)
        self.entity_description = description
        self._attr_unique_id = f"{dsn}_{description.key}"


class BradfordWhiteConnectEnergyEntity(
    BradfordWhiteConnectEntity[BradfordWhiteConnectEnergyCoordinator]
):
    """Base entity for entities that use data from the energy coordinator."""

    @property
    def available(self) -> bool:
        """Return True only when this device is present in the latest update."""
        return super().available and self._dsn in self.coordinator.data

    @property
    def energy_usage(self) -> float | None:
        """Return this device's energy usage, or None if absent this cycle."""
        device_usage = self.coordinator.data.get(self._dsn)
        if device_usage is None:
            return None
        return device_usage.get(self._energy_type)
