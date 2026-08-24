from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util

from .coordinator import ZHAGatewayCoordinator
from .helpers import get_zha_gateway_and_entry

DOMAIN = "zha_connectivity_sensor"
ZHA_UNAVAILABLE_ISSUE = "zha_unavailable"
ZHA_UNAVAILABLE_THRESHOLD = timedelta(minutes=15)
_DATA_UNAVAILABLE_SINCE = "unavailable_since"

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

    # Kept in hass.data, not a closure, so an in-progress outage survives
    # a reload of this entry.
    domain_data = hass.data.setdefault(DOMAIN, {})

    @callback
    def _check_zha_availability() -> None:
        """Raise/clear a repair issue based on how long ZHA's been down."""
        current_gateway, _ = coordinator.data
        issue_active = (
            ir.async_get(hass).async_get_issue(DOMAIN, ZHA_UNAVAILABLE_ISSUE)
            is not None
        )

        if current_gateway is not None:
            if issue_active:
                ir.async_delete_issue(hass, DOMAIN, ZHA_UNAVAILABLE_ISSUE)
            domain_data[_DATA_UNAVAILABLE_SINCE] = None
            return

        unavailable_since = domain_data.get(_DATA_UNAVAILABLE_SINCE)
        if unavailable_since is None:
            domain_data[_DATA_UNAVAILABLE_SINCE] = dt_util.utcnow()
            return

        if (
            not issue_active
            and dt_util.utcnow() - unavailable_since >= ZHA_UNAVAILABLE_THRESHOLD
        ):
            ir.async_create_issue(
                hass,
                DOMAIN,
                ZHA_UNAVAILABLE_ISSUE,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="zha_unavailable",
            )

    # Registered before the first refresh so that refresh's own result
    # isn't missed -- a coordinator notifies listeners on every refresh,
    # including the first.
    entry.async_on_unload(coordinator.async_add_listener(_check_zha_availability))

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
