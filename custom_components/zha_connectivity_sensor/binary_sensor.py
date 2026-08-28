from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.zha.helpers import SIGNAL_ADD_ENTITIES
from homeassistant.util import dt as dt_util
from zigpy.types import EUI64

from . import ZHAConnectivityConfigEntry
from .coordinator import ZHAGatewayCoordinator
from .helpers import (
    get_enable_new_devices,
    get_zha_gateway_and_entry,
    ieee_from_device_entry,
    zha_identifier,
)

_LOGGER = logging.getLogger(__name__)

CONNECTIVITY_DESCRIPTION = BinarySensorEntityDescription(
    key="connectivity",
    translation_key="connectivity",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
)


def _unique_id(ieee_obj: Any) -> str:
    """Return the unique_id for a given IEEE address."""
    return f"zha_connectivity_sensor_{str(ieee_obj).replace(':', '')}"


def _resolve_device_entry(
    hass: HomeAssistant, ieee_obj: Any, zha_entry_id: str
) -> DeviceEntry | None:
    """Look up the ZHA-owned device entry for the given IEEE address."""
    return dr.async_get(hass).async_get_device_by_identifier(
        zha_identifier(ieee_obj), zha_entry_id
    )


def _known_sensors_from_registry(
    hass: HomeAssistant,
    config_entry: ZHAConnectivityConfigEntry,
    coordinator: ZHAGatewayCoordinator,
) -> list[ZHAConnectivitySensor]:
    """Reconstruct sensors for already-known devices without a live gateway.

    Used when ZHA is unavailable at setup so existing entities still report
    "disconnected" instead of "unavailable".
    """
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    sensors: list[ZHAConnectivitySensor] = []
    for reg_entry in er.async_entries_for_config_entry(
        entity_registry, config_entry.entry_id
    ):
        if reg_entry.device_id is None:
            _LOGGER.warning(
                "Skipping %s: no linked device in the registry", reg_entry.entity_id
            )
            continue
        device_entry = device_registry.async_get(reg_entry.device_id)
        if device_entry is None:
            _LOGGER.warning(
                "Skipping %s: device %s no longer in the device registry",
                reg_entry.entity_id,
                reg_entry.device_id,
            )
            continue
        ieee = ieee_from_device_entry(device_entry)
        if ieee is None:
            _LOGGER.warning(
                "Skipping device %s: no ZHA identifier found", device_entry.id
            )
            continue
        try:
            ieee_obj = EUI64.convert(ieee)
        except (ValueError, AssertionError, TypeError):
            _LOGGER.warning(
                "Skipping device %s: %r is not a valid IEEE address",
                device_entry.id,
                ieee,
            )
            continue
        sensors.append(ZHAConnectivitySensor(coordinator, ieee_obj, device_entry, True))
    return sensors


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ZHAConnectivityConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ZHA Connectivity Sensor sensors from a config entry."""
    enable_new_devices = get_enable_new_devices(config_entry)
    coordinator = config_entry.runtime_data

    def _build_sensor(
        ieee_obj: Any, zha_entry_id: str, enable_by_default: bool
    ) -> ZHAConnectivitySensor | None:
        """Build a sensor for the given IEEE address, or None if not yet linkable."""
        device_entry = _resolve_device_entry(hass, ieee_obj, zha_entry_id)
        if device_entry is None:
            _LOGGER.warning(
                "Skipping connectivity sensor for %s: device not yet in the "
                "device registry",
                ieee_obj,
            )
            return None
        return ZHAConnectivitySensor(
            coordinator, ieee_obj, device_entry, enable_by_default
        )

    @callback
    def _handle_add_entities() -> None:
        """Add sensors for any newly paired ZHA devices.

        Resolves the gateway directly instead of via coordinator.data, since
        this fires on ZHA's own SIGNAL_ADD_ENTITIES dispatch and needs the
        state at that exact instant, not the coordinator's up-to-1s-stale
        snapshot.
        """
        current_gateway, current_zha_entry = get_zha_gateway_and_entry(hass)
        if current_gateway is None:
            return

        entity_registry = er.async_get(hass)
        existing_unique_ids = {
            entry.unique_id
            for entry in er.async_entries_for_config_entry(
                entity_registry, config_entry.entry_id
            )
        }

        new_sensors = [
            sensor
            for ieee in current_gateway.devices.keys()
            if _unique_id(ieee) not in existing_unique_ids
            and (
                sensor := _build_sensor(
                    ieee, current_zha_entry.entry_id, enable_new_devices
                )
            )
            is not None
        ]
        if new_sensors:
            _LOGGER.debug("Adding sensors for %d new ZHA device(s)", len(new_sensors))
            async_add_entities(new_sensors)

    config_entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_ADD_ENTITIES, _handle_add_entities)
    )

    gateway, zha_entry = coordinator.data

    if gateway is not None and gateway.devices:
        _LOGGER.debug(
            "Setting up connectivity sensors for %d ZHA devices", len(gateway.devices)
        )
        # enable_new_devices only applies to devices discovered later.
        initial_sensors = [
            sensor
            for ieee in gateway.devices.keys()
            if (sensor := _build_sensor(ieee, zha_entry.entry_id, True)) is not None
        ]
        if initial_sensors:
            async_add_entities(initial_sensors)
        return

    # No live gateway (or no devices loaded yet); fall back to the registry.
    _LOGGER.warning(
        "ZHA gateway unavailable during setup; recreating known sensors from "
        "the registry so they report disconnected instead of unavailable"
    )
    known_sensors = _known_sensors_from_registry(hass, config_entry, coordinator)
    if known_sensors:
        async_add_entities(known_sensors)


class ZHAConnectivitySensor(
    CoordinatorEntity[ZHAGatewayCoordinator], BinarySensorEntity
):
    """Sensor exposing ZHA device connectivity and last seen time."""

    entity_description = CONNECTIVITY_DESCRIPTION
    _attr_has_entity_name = True
    _unrecorded_attributes = frozenset({MATCH_ALL})

    def __init__(
        self,
        coordinator: ZHAGatewayCoordinator,
        ieee_obj: Any,  # zigpy EUI64
        device_entry: DeviceEntry,
        enable_by_default: bool,
    ) -> None:
        """Initialise the sensor.

        device_entry is set directly on self.device_entry, not via
        device_info, to link to ZHA's device without claiming it.
        """
        super().__init__(coordinator)
        self._ieee_obj = ieee_obj
        self._attr_entity_registry_enabled_default = enable_by_default
        self._attr_unique_id = _unique_id(ieee_obj)
        self.device_entry = device_entry

    @property
    def _device_obj(self) -> Any | None:
        """Return the current ZHA device object, or None if unavailable."""
        gateway, _ = self.coordinator.data
        if gateway is None:
            return None
        return gateway.devices.get(self._ieee_obj)

    @property
    def available(self) -> bool:
        """Return entity availability.

        A down gateway reports "disconnected" (is_on=False), not
        unavailable. Only flips unavailable when this specific device is
        gone from an otherwise-live gateway, e.g. unpaired from ZHA.
        """
        if not super().available:
            return False
        gateway, _ = self.coordinator.data
        if gateway is None:
            return True
        return self._device_obj is not None

    @property
    def is_on(self) -> bool | None:
        """Return whether the device is currently connected."""
        device_obj = self._device_obj
        if device_obj is None:
            return False
        raw_available = device_obj.available
        return bool(raw_available) if raw_available is not None else None

    @property
    def icon(self) -> str:
        """Return icon reflecting current connectivity state."""
        return "mdi:access-point" if self.is_on else "mdi:access-point-off"

    @property
    def extra_state_attributes(self) -> dict[str, datetime | None]:
        """Return last seen time as a state attribute."""
        device_obj = self._device_obj
        last_seen: datetime | None = None
        if device_obj is not None and device_obj.last_seen is not None:
            try:
                last_seen = dt_util.utc_from_timestamp(device_obj.last_seen)
            except (ValueError, OSError, OverflowError):
                _LOGGER.warning(
                    "Invalid last_seen timestamp %r for %s",
                    device_obj.last_seen,
                    self._ieee_obj,
                )
        return {"last_seen": last_seen}
