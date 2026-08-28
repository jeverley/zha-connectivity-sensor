from __future__ import annotations

from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .coordinator import ZHAGatewayCoordinator
from .helpers import get_zha_gateway_and_entry

DOMAIN = "zha_connectivity_sensor"

ZHAConnectivityConfigEntry = ConfigEntry[ZHAGatewayCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ZHAConnectivityConfigEntry) -> bool:
    """Set up the ZHA Connectivity Sensor from a config entry."""
    # Retry via ConfigEntryNotReady only on first-ever setup. If we already
    # have known entities, let setup proceed; binary_sensor.py falls back
    # to the registry and reports "disconnected" instead.
    gateway, _ = get_zha_gateway_and_entry(hass)
    if gateway is None:
        entity_registry = er.async_get(hass)
        has_known_devices = any(
            er.async_entries_for_config_entry(entity_registry, entry.entry_id)
        )
        if not has_known_devices:
            raise ConfigEntryNotReady("ZHA gateway is not ready yet")

    coordinator = ZHAGatewayCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, ["binary_sensor"])
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: ZHAConnectivityConfigEntry
) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ZHAConnectivityConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, ["binary_sensor"])
