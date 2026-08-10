"""DataUpdateCoordinator for ZHA gateway availability.

Resolves the ZHA gateway once per tick and shares the result across every
ZHAConnectivitySensor, instead of each entity independently re-resolving
it on every poll.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .helpers import get_zha_gateway_and_entry

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=1)

_GatewayData = tuple[Any, ConfigEntry] | tuple[None, None]


class ZHAGatewayCoordinator(DataUpdateCoordinator[_GatewayData]):
    """Coordinator that resolves the ZHA gateway once per tick.

    self.data is (gateway, owning ZHA config entry), or (None, None) if
    unavailable. Never raises: an unready ZHA gateway is an expected state,
    not an update failure.
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="zha_connectivity_sensor_gateway",
            update_interval=UPDATE_INTERVAL,
        )

    async def _async_update_data(self) -> _GatewayData:
        """Return (gateway, zha_entry), or (None, None) if unavailable."""
        return get_zha_gateway_and_entry(self.hass)
