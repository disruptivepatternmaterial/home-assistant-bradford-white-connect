"""The water heater platform for the Bradford White Connect integration."""

from datetime import datetime, timezone
import logging
from typing import Any

from bradford_white_connect_client.constants import BradfordWhiteConnectHeatingModes
from bradford_white_connect_client.helper import BradfordWhiteConnectHelper
from bradford_white_connect_client.types import Device
from homeassistant.components.water_heater import (
    STATE_ECO,
    STATE_ELECTRIC,
    STATE_HEAT_PUMP,
    STATE_HIGH_DEMAND,
    STATE_OFF,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BradfordWhiteConnectData
from .const import DOMAIN
from .coordinator import BradfordWhiteConnectStatusCoordinator
from .entity import BradfordWhiteConnectStatusEntity

MODE_HA_TO_BRADFORDWHITE = {
    STATE_ECO: BradfordWhiteConnectHeatingModes.HYBRID,
    STATE_ELECTRIC: BradfordWhiteConnectHeatingModes.ELECTRIC,
    STATE_HEAT_PUMP: BradfordWhiteConnectHeatingModes.HEAT_PUMP,
    STATE_HIGH_DEMAND: BradfordWhiteConnectHeatingModes.HYBRID_PLUS,
    STATE_OFF: BradfordWhiteConnectHeatingModes.VACATION,
}
MODE_BRADFORDWHITE_TO_HA = {
    BradfordWhiteConnectHeatingModes.ELECTRIC: STATE_ELECTRIC,
    BradfordWhiteConnectHeatingModes.HEAT_PUMP: STATE_HEAT_PUMP,
    BradfordWhiteConnectHeatingModes.HYBRID_PLUS: STATE_HIGH_DEMAND,
    BradfordWhiteConnectHeatingModes.HYBRID: STATE_ECO,
    BradfordWhiteConnectHeatingModes.VACATION: STATE_OFF,
}

# Priority list for operation mode to use when exiting away mode
# Will use the first mode that is supported by the device
DEFAULT_OPERATION_MODE_PRIORITY = [
    BradfordWhiteConnectHeatingModes.HEAT_PUMP,
    BradfordWhiteConnectHeatingModes.HYBRID,
    BradfordWhiteConnectHeatingModes.ELECTRIC,
]

_LOGGER = logging.getLogger(__name__)


def _to_float(value: Any) -> float | None:
    """Coerce a device property value to float, or None if not numeric.

    ``Property.value`` is typed ``Optional[str]`` upstream, so a numeric
    reading can arrive as a string; Home Assistant requires a real ``float``
    (or ``None``) for temperatures.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Bradford White Connect water heater platform."""
    data: BradfordWhiteConnectData = hass.data[DOMAIN][entry.entry_id]

    # Add water heater entities for each device
    async_add_entities(
        BradfordWhiteConnectWaterHeaterEntity(data.status_coordinator, dsn, device)
        for dsn, device in data.status_coordinator.data.items()
    )


class BradfordWhiteConnectWaterHeaterEntity(
    BradfordWhiteConnectStatusEntity, WaterHeaterEntity
):
    """The water heater entity for the Bradford White Connect integration."""

    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.FAHRENHEIT

    def __init__(
        self,
        coordinator: BradfordWhiteConnectStatusCoordinator,
        dsn: str,
        device: Device,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, dsn, device)
        self._attr_unique_id = dsn

    def _supported_vendor_modes(self) -> list[int]:
        """Return the vendor heating-mode list for this appliance, or [] if unknown."""
        model_prop = self.device.properties.get("appliance_model_out")
        if model_prop is None or not getattr(model_prop, "value", None):
            return []
        appliance_model = model_prop.value.strip()
        if not appliance_model:
            return []
        return list(
            BradfordWhiteConnectHelper.get_appliance_model_heating_modes(
                appliance_model
            )
        )

    @property
    def operation_list(self) -> list[str]:
        """Return the list of supported operation modes.

        Home Assistant requires ``current_operation`` to be a member of
        ``operation_list``. Because ``current_operation`` is derived from the
        live ``current_heat_mode`` while this list is derived from the model's
        published mode set, we always fold the current operation in so the
        two can't disagree (this covers unknown/newer models whose mode set
        isn't in the upstream helper, where the list would otherwise collapse
        to ``[STATE_OFF]`` while the unit reports a real mode).
        """
        ha_modes = [
            MODE_BRADFORDWHITE_TO_HA.get(mode)
            for mode in self._supported_vendor_modes()
            if MODE_BRADFORDWHITE_TO_HA.get(mode)
        ]
        current = self.current_operation
        if current and current not in ha_modes:
            ha_modes.append(current)
        return ha_modes or [STATE_OFF]

    @property
    def supported_features(self) -> WaterHeaterEntityFeature:
        """Return the list of supported features."""
        support_flags = WaterHeaterEntityFeature.TARGET_TEMPERATURE

        # Operation mode is supported only when the model exposes more than
        # one vendor mode. This is derived from the (static) model mode set
        # rather than ``operation_list`` so the feature flag doesn't flap as
        # the live ``current_operation`` is folded into ``operation_list``.
        if len(self._supported_vendor_modes()) > 1:
            support_flags |= WaterHeaterEntityFeature.OPERATION_MODE

        support_flags |= WaterHeaterEntityFeature.AWAY_MODE

        return support_flags

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        tank_temp = self.device.properties.get("tank_temp")
        return _to_float(tank_temp.value) if tank_temp else None

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        water_setpoint_out = self.device.properties.get("water_setpoint_out")
        return _to_float(water_setpoint_out.value) if water_setpoint_out else None

    @property
    def min_temp(self) -> float | None:
        """Return the minimum temperature."""
        water_setpoint_min = self.device.properties.get("water_setpoint_min")
        return _to_float(water_setpoint_min.value) if water_setpoint_min else None

    @property
    def max_temp(self) -> float | None:
        """Return the maximum temperature."""
        water_setpoint_max = self.device.properties.get("water_setpoint_max")
        return _to_float(water_setpoint_max.value) if water_setpoint_max else None

    @property
    def current_operation(self) -> str:
        """Return the mode the appliance is actually operating in.

        Uses ``current_heat_mode`` — the firmware's live operating mode,
        which is what the unit's own front panel displays (verified: panel
        "Hybrid" ⇔ ``current_heat_mode == HYBRID``). This is distinct from
        ``user_heat_mode`` (the last *requested* mode), which is surfaced
        separately as the "Requested heat mode" diagnostic sensor.

        Note ``current_heat_mode`` is device-pushed telemetry: if the
        appliance loses connectivity it stops updating, so a stale value
        means the unit is offline, not that the mode is wrong.
        """
        current_heat_mode = self.device.properties.get("current_heat_mode")
        if current_heat_mode is None or current_heat_mode.value is None:
            return STATE_OFF
        return MODE_BRADFORDWHITE_TO_HA.get(current_heat_mode.value, STATE_OFF)

    @property
    def is_away_mode_on(self):
        """Return True if the appliance is actually operating in vacation."""
        current_heat_mode = self.device.properties.get("current_heat_mode")
        if current_heat_mode is None:
            return False
        return current_heat_mode.value == BradfordWhiteConnectHeatingModes.VACATION

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set new target operation mode."""
        if operation_mode not in self.operation_list:
            raise HomeAssistantError("Operation mode not supported")

        vendor_mode = MODE_HA_TO_BRADFORDWHITE.get(operation_mode)
        if vendor_mode is not None:
            _LOGGER.info("Setting operation mode to %s", operation_mode)
            await self.client.set_device_heat_mode(self.device, vendor_mode)
            self.coordinator.shared_data["last_api_set_datetime"] = datetime.now(
                timezone.utc
            )
            await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get("temperature")
        if temperature is not None:
            _LOGGER.info("Setting temperature to %s", temperature)
            await self.client.update_device_set_point(self.device, temperature)
            self.coordinator.shared_data["last_api_set_datetime"] = datetime.now(
                timezone.utc
            )
            await self.coordinator.async_request_refresh()

    async def async_turn_away_mode_on(self) -> None:
        """Turn away mode on."""
        _LOGGER.info("Setting away mode on")
        await self.client.set_device_heat_mode(
            self.device, BradfordWhiteConnectHeatingModes.VACATION
        )
        self.coordinator.shared_data["last_api_set_datetime"] = datetime.now(
            timezone.utc
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_away_mode_off(self) -> None:
        """Turn away mode off by switching back to the best supported mode.

        Picks the first entry from ``DEFAULT_OPERATION_MODE_PRIORITY`` that
        the appliance actually supports. If none of the preferred modes are
        in the supported list (or the list is empty because the model is
        unknown/newer), falls back to the first non-vacation mode the
        appliance reports, and finally to the top default-priority mode so a
        user is never locked into away mode just because we don't recognise
        the model.
        """
        supported_modes = [
            mode
            for mode in self._supported_vendor_modes()
            if mode != BradfordWhiteConnectHeatingModes.VACATION
        ]

        target_mode: int | None = next(
            (mode for mode in DEFAULT_OPERATION_MODE_PRIORITY if mode in supported_modes),
            None,
        )
        if target_mode is None:
            target_mode = (
                supported_modes[0]
                if supported_modes
                else DEFAULT_OPERATION_MODE_PRIORITY[0]
            )

        _LOGGER.info("Setting away mode off, switching to mode: %s", target_mode)
        await self.client.set_device_heat_mode(self.device, target_mode)
        self.coordinator.shared_data["last_api_set_datetime"] = datetime.now(
            timezone.utc
        )
        await self.coordinator.async_request_refresh()
