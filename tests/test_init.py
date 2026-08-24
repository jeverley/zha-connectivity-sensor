"""Functional tests for __init__.py.

Area C: repair issue threshold. Area E: setup-time gating (cold start).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from freezegun import freeze_time
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry
from zigpy.types import EUI64

from custom_components.zha_connectivity_sensor import (
    DOMAIN,
    ZHA_UNAVAILABLE_ISSUE,
    ZHA_UNAVAILABLE_THRESHOLD,
    _DATA_UNAVAILABLE_SINCE,
)
from custom_components.zha_connectivity_sensor.binary_sensor import _unique_id
from custom_components.zha_connectivity_sensor.coordinator import ZHAGatewayCoordinator

from .conftest import GatewayProxyState

pytestmark = pytest.mark.asyncio

IEEE = "00:11:22:33:44:55:66:77"
IEEE_OBJ = EUI64.convert(IEEE)


def _issue_active(issue_registry: ir.IssueRegistry) -> bool:
    return issue_registry.async_get_issue(DOMAIN, ZHA_UNAVAILABLE_ISSUE) is not None


# --- Area C: repair issue threshold ---------------------------------------
#
# Every test here seeds a known prior sensor first so setup takes the
# registry-fallback path rather than ConfigEntryNotReady (that's Area E's
# concern) -- these are purely about the repair-issue bookkeeping once
# setup has already succeeded.


async def _setup(hass: HomeAssistant, config_entry: MockConfigEntry) -> ZHAGatewayCoordinator:
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry.runtime_data


async def test_unavailable_since_set_on_first_down_tick(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_zha_device,
    seed_known_sensor,
    gateway_proxy: GatewayProxyState,
    issue_registry: ir.IssueRegistry,
):
    seed_known_sensor(make_zha_device(IEEE), IEEE_OBJ)
    gateway_proxy.not_ready()

    with freeze_time("2026-01-01 00:00:00"):
        await _setup(hass, config_entry)

    assert hass.data[DOMAIN][_DATA_UNAVAILABLE_SINCE] is not None
    assert not _issue_active(issue_registry)


async def test_unavailable_since_not_reset_on_subsequent_ticks(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_zha_device,
    seed_known_sensor,
    gateway_proxy: GatewayProxyState,
):
    seed_known_sensor(make_zha_device(IEEE), IEEE_OBJ)
    gateway_proxy.not_ready()

    with freeze_time("2026-01-01 00:00:00") as frozen:
        coordinator = await _setup(hass, config_entry)
        first = hass.data[DOMAIN][_DATA_UNAVAILABLE_SINCE]

        frozen.tick(timedelta(minutes=5))
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        assert hass.data[DOMAIN][_DATA_UNAVAILABLE_SINCE] == first


async def test_issue_created_past_threshold(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_zha_device,
    seed_known_sensor,
    gateway_proxy: GatewayProxyState,
    issue_registry: ir.IssueRegistry,
):
    seed_known_sensor(make_zha_device(IEEE), IEEE_OBJ)
    gateway_proxy.not_ready()

    with freeze_time("2026-01-01 00:00:00") as frozen:
        coordinator = await _setup(hass, config_entry)
        assert not _issue_active(issue_registry)

        frozen.tick(ZHA_UNAVAILABLE_THRESHOLD + timedelta(seconds=1))
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        assert _issue_active(issue_registry)


async def test_issue_not_recreated_once_active(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_zha_device,
    seed_known_sensor,
    gateway_proxy: GatewayProxyState,
    issue_registry: ir.IssueRegistry,
):
    seed_known_sensor(make_zha_device(IEEE), IEEE_OBJ)
    gateway_proxy.not_ready()

    with freeze_time("2026-01-01 00:00:00") as frozen:
        coordinator = await _setup(hass, config_entry)

        frozen.tick(ZHA_UNAVAILABLE_THRESHOLD + timedelta(seconds=1))
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        first_issue = issue_registry.async_get_issue(DOMAIN, ZHA_UNAVAILABLE_ISSUE)

        frozen.tick(timedelta(minutes=1))
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        second_issue = issue_registry.async_get_issue(DOMAIN, ZHA_UNAVAILABLE_ISSUE)

        assert first_issue is second_issue


async def test_issue_cleared_when_gateway_recovers(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_zha_device,
    seed_known_sensor,
    gateway_proxy: GatewayProxyState,
    issue_registry: ir.IssueRegistry,
):
    seed_known_sensor(make_zha_device(IEEE), IEEE_OBJ)
    gateway_proxy.not_ready()

    with freeze_time("2026-01-01 00:00:00") as frozen:
        coordinator = await _setup(hass, config_entry)

        frozen.tick(ZHA_UNAVAILABLE_THRESHOLD + timedelta(seconds=1))
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert _issue_active(issue_registry)

        gateway_proxy.ready_with(IEEE_OBJ)
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        assert not _issue_active(issue_registry)
        assert hass.data[DOMAIN][_DATA_UNAVAILABLE_SINCE] is None


async def test_unavailable_since_survives_reload(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_zha_device,
    seed_known_sensor,
    gateway_proxy: GatewayProxyState,
):
    seed_known_sensor(make_zha_device(IEEE), IEEE_OBJ)
    gateway_proxy.not_ready()

    with freeze_time("2026-01-01 00:00:00") as frozen:
        await _setup(hass, config_entry)
        first = hass.data[DOMAIN][_DATA_UNAVAILABLE_SINCE]

        frozen.tick(timedelta(minutes=1))
        assert await hass.config_entries.async_reload(config_entry.entry_id)
        await hass.async_block_till_done()

        assert hass.data[DOMAIN][_DATA_UNAVAILABLE_SINCE] == first


# --- Area E: setup-time gating (cold start / first-ever setup) -----------
#
# Distinct from Area C/B: no prior registry entries exist yet, so there's
# nothing to fall back to -- this is __init__.py's own gate, before setup
# is ever forwarded to binary_sensor.py at all.


async def test_first_setup_retries_when_zha_not_ready(
    hass: HomeAssistant, config_entry: MockConfigEntry, gateway_proxy: GatewayProxyState
):
    gateway_proxy.not_ready()

    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_first_setup_succeeds_when_gateway_ready(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
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
