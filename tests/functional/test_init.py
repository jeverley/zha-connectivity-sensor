"""Functional tests for __init__.py.

Area E: setup-time gating (cold start).
"""

from __future__ import annotations

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from zigpy.types import EUI64

from custom_components.zha_connectivity_sensor import DOMAIN
from custom_components.zha_connectivity_sensor.binary_sensor import _unique_id

from .conftest import GatewayProxyState

pytestmark = pytest.mark.asyncio

IEEE = "00:11:22:33:44:55:66:77"
IEEE_OBJ = EUI64.convert(IEEE)


# --- Area E: setup-time gating (cold start / first-ever setup) -----------
#
# No prior registry entries exist yet, so there's nothing to fall back to:
# this is __init__.py's own gate, before setup is ever forwarded to
# binary_sensor.py at all.


async def test_first_setup_retries_when_zha_not_ready(
    hass: HomeAssistant, config_entry, gateway_proxy: GatewayProxyState
):
    gateway_proxy.not_ready()

    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_first_setup_succeeds_when_gateway_ready(
    hass: HomeAssistant,
    config_entry,
    make_zha_device,
    gateway_proxy: GatewayProxyState,
):
    make_zha_device(IEEE)
    gateway_proxy.ready_with(IEEE_OBJ)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    entity_id = er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, _unique_id(IEEE_OBJ)
    )
    assert entity_id is not None
