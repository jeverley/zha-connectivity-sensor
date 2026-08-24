"""Functional tests for binary_sensor.py.

Area A: availability/is_on semantics. Area B: registry fallback and
recovery from it. Area D: device linkage (the 2026.8 single-owning-
config-entry contract). Plus the SIGNAL_ADD_ENTITIES hot-add path.
"""

from __future__ import annotations

import logging

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from zigpy.types import EUI64

from custom_components.zha_connectivity_sensor import DOMAIN
from custom_components.zha_connectivity_sensor.binary_sensor import (
    SIGNAL_ADD_ENTITIES,
    ZHAConnectivitySensor,
    _unique_id,
)
from custom_components.zha_connectivity_sensor.coordinator import ZHAGatewayCoordinator

from .conftest import FakeDevice, FakeGateway, GatewayProxyState

pytestmark = pytest.mark.asyncio

IEEE = "00:11:22:33:44:55:66:77"
IEEE_OBJ = EUI64.convert(IEEE)


# --- Area A: availability / is_on semantics ------------------------------
#
# The coordinator drives a real refresh through gateway_proxy (the same
# patched HA-boundary every other area uses), rather than having
# .data/.last_update_success poked by hand -- so these tests exercise the
# actual _async_update_data path, not just the properties that read it.


async def _sensor(
    hass,
    config_entry,
    make_zha_device,
    gateway_proxy: GatewayProxyState,
    *,
    gateway: FakeGateway | None,
    last_update_success: bool = True,
    enable_by_default: bool = True,
) -> ZHAConnectivitySensor:
    """Build a sensor backed by a coordinator that has actually refreshed.

    gateway=None drives a real "not ready" refresh (a genuine, expected
    coordinator outcome, same as ZHA being down). last_update_success=False
    can't be produced through a real refresh -- this coordinator's
    _async_update_data never raises by design -- so that one case is set
    directly afterwards, to simulate an artificial coordinator failure.
    """
    device_entry = make_zha_device(IEEE)
    if gateway is None:
        gateway_proxy.not_ready()
    else:
        gateway_proxy.ready(gateway)

    coordinator = ZHAGatewayCoordinator(hass, config_entry)
    await coordinator.async_refresh()

    if not last_update_success:
        coordinator.last_update_success = False

    return ZHAConnectivitySensor(coordinator, IEEE_OBJ, device_entry, enable_by_default)


async def test_available_connected(
    hass: HomeAssistant, config_entry, make_zha_device, gateway_proxy: GatewayProxyState
):
    gateway = FakeGateway(devices={IEEE_OBJ: FakeDevice(IEEE_OBJ, available=True)})
    sensor = await _sensor(hass, config_entry, make_zha_device, gateway_proxy, gateway=gateway)
    assert sensor.is_on is True
    assert sensor.available is True


async def test_available_disconnected_not_unavailable(
    hass: HomeAssistant, config_entry, make_zha_device, gateway_proxy: GatewayProxyState
):
    gateway = FakeGateway(devices={IEEE_OBJ: FakeDevice(IEEE_OBJ, available=False)})
    sensor = await _sensor(hass, config_entry, make_zha_device, gateway_proxy, gateway=gateway)
    assert sensor.is_on is False
    assert sensor.available is True


async def test_device_missing_from_live_gateway_is_unavailable(
    hass: HomeAssistant, config_entry, make_zha_device, gateway_proxy: GatewayProxyState
):
    gateway = FakeGateway(devices={})  # this device isn't in it -- e.g. unpaired
    sensor = await _sensor(hass, config_entry, make_zha_device, gateway_proxy, gateway=gateway)
    assert sensor.available is False


async def test_gateway_down_reports_disconnected(
    hass: HomeAssistant, config_entry, make_zha_device, gateway_proxy: GatewayProxyState
):
    sensor = await _sensor(hass, config_entry, make_zha_device, gateway_proxy, gateway=None)
    assert sensor.is_on is False
    assert sensor.available is True


async def test_is_on_none_when_device_available_is_none(
    hass: HomeAssistant, config_entry, make_zha_device, gateway_proxy: GatewayProxyState
):
    gateway = FakeGateway(devices={IEEE_OBJ: FakeDevice(IEEE_OBJ, available=None)})
    sensor = await _sensor(hass, config_entry, make_zha_device, gateway_proxy, gateway=gateway)
    assert sensor.is_on is None


async def test_unavailable_when_coordinator_update_failed(
    hass: HomeAssistant, config_entry, make_zha_device, gateway_proxy: GatewayProxyState
):
    gateway = FakeGateway(devices={IEEE_OBJ: FakeDevice(IEEE_OBJ, available=True)})
    sensor = await _sensor(
        hass,
        config_entry,
        make_zha_device,
        gateway_proxy,
        gateway=gateway,
        last_update_success=False,
    )
    assert sensor.available is False


async def test_enable_by_default_false_disables_registry_entry(
    hass: HomeAssistant, config_entry, make_zha_device, gateway_proxy: GatewayProxyState
):
    gateway = FakeGateway(devices={IEEE_OBJ: FakeDevice(IEEE_OBJ, available=True)})
    sensor = await _sensor(
        hass, config_entry, make_zha_device, gateway_proxy, gateway=gateway, enable_by_default=False
    )
    assert sensor.entity_registry_enabled_default is False


async def test_last_seen_converts_valid_timestamp(
    hass: HomeAssistant, config_entry, make_zha_device, gateway_proxy: GatewayProxyState
):
    gateway = FakeGateway(devices={IEEE_OBJ: FakeDevice(IEEE_OBJ, last_seen=1700000000.0)})
    sensor = await _sensor(hass, config_entry, make_zha_device, gateway_proxy, gateway=gateway)
    assert sensor.extra_state_attributes["last_seen"] == dt_util.utc_from_timestamp(
        1700000000.0
    )


async def test_last_seen_invalid_timestamp_degrades_to_none(
    hass: HomeAssistant, config_entry, make_zha_device, gateway_proxy: GatewayProxyState, caplog
):
    gateway = FakeGateway(devices={IEEE_OBJ: FakeDevice(IEEE_OBJ, last_seen=float("inf"))})
    sensor = await _sensor(hass, config_entry, make_zha_device, gateway_proxy, gateway=gateway)
    with caplog.at_level(logging.WARNING):
        attrs = sensor.extra_state_attributes
    assert attrs["last_seen"] is None
    assert "Invalid last_seen" in caplog.text


# --- Area B: registry fallback and recovery -------------------------------


async def test_registry_fallback_recreates_known_sensor(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_zha_device,
    seed_known_sensor,
    gateway_proxy: GatewayProxyState,
):
    device_entry = make_zha_device(IEEE)
    seed_known_sensor(device_entry, IEEE_OBJ)
    gateway_proxy.not_ready()

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, _unique_id(IEEE_OBJ)
    )
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "off"  # disconnected, not unavailable


async def test_registry_fallback_skips_entry_without_device(
    hass: HomeAssistant, config_entry: MockConfigEntry, gateway_proxy: GatewayProxyState
):
    entity_registry = er.async_get(hass)
    orphan = entity_registry.async_get_or_create(
        domain="binary_sensor",
        platform=DOMAIN,
        unique_id="zha_connectivity_sensor_orphan",
        config_entry=config_entry,
    )
    gateway_proxy.not_ready()

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # Skipped, not recreated as a live entity -- no state exists for it.
    assert hass.states.get(orphan.entity_id) is None


async def test_registry_fallback_skips_device_missing_zha_identifier(
    hass: HomeAssistant, config_entry: MockConfigEntry, gateway_proxy: GatewayProxyState
):
    device_registry = dr.async_get(hass)
    other_entry = MockConfigEntry(domain="not_zha")
    other_entry.add_to_hass(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id=other_entry.entry_id,
        identifiers={("not_zha", "abc")},
    )
    entity_registry = er.async_get(hass)
    seeded = entity_registry.async_get_or_create(
        domain="binary_sensor",
        platform=DOMAIN,
        unique_id="zha_connectivity_sensor_no_ieee",
        config_entry=config_entry,
        device_id=device_entry.id,
    )
    gateway_proxy.not_ready()

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # Skipped (no ZHA identifier to resolve), not recreated as a live entity.
    assert hass.states.get(seeded.entity_id) is None


async def test_registry_fallback_not_taken_when_gateway_live(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_zha_device,
    seed_known_sensor,
    gateway_proxy: GatewayProxyState,
):
    device_entry = make_zha_device(IEEE)
    seed_known_sensor(device_entry, IEEE_OBJ)
    gateway_proxy.ready_with(IEEE_OBJ, available=True)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, _unique_id(IEEE_OBJ)
    )
    state = hass.states.get(entity_id)
    assert state.state == "on"


async def test_recovers_after_gateway_comes_back(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_zha_device,
    seed_known_sensor,
    gateway_proxy: GatewayProxyState,
):
    """ZHA configured but not loaded yet at startup, then finishes loading."""
    device_entry = make_zha_device(IEEE)
    seed_known_sensor(device_entry, IEEE_OBJ)
    gateway_proxy.not_ready()

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, _unique_id(IEEE_OBJ)
    )
    assert hass.states.get(entity_id).state == "off"

    # ZHA finishes loading -- the *same* entity should pick this up without
    # being re-created, since is_on/available read fresh from
    # coordinator.data on every access.
    gateway_proxy.ready_with(IEEE_OBJ, available=True, last_seen=1700000000.0)
    coordinator: ZHAGatewayCoordinator = config_entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "on"
    assert state.attributes["last_seen"] is not None


async def test_hot_add_new_device_via_signal(
    hass: HomeAssistant,
    make_zha_device,
    gateway_proxy: GatewayProxyState,
):
    """A device pairs with ZHA while this integration is already running.

    Uses its own config entry with enable_new_devices=True (the shared
    `config_entry` fixture defaults it False) so the newly hot-added
    sensor actually goes live instead of arriving disabled -- that
    False-by-default behavior is covered separately by
    test_enable_by_default_false_disables_registry_entry.
    """
    config_entry = MockConfigEntry(
        domain=DOMAIN, data={"enable_new_devices": True}, options={}
    )
    config_entry.add_to_hass(hass)

    gateway = FakeGateway()
    gateway_proxy.ready(gateway)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id_before = er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, _unique_id(IEEE_OBJ)
    )
    assert entity_id_before is None

    # ZHA finishes pairing: registers the device, adds it to the gateway,
    # then announces it via its own dispatcher signal.
    make_zha_device(IEEE)
    gateway.devices[IEEE_OBJ] = FakeDevice(IEEE_OBJ, available=True)
    async_dispatcher_send(hass, SIGNAL_ADD_ENTITIES)
    await hass.async_block_till_done()

    entity_id = er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, _unique_id(IEEE_OBJ)
    )
    assert entity_id is not None
    assert hass.states.get(entity_id).state == "on"


# --- Area D: device linkage -----------------------------------------------


async def test_sensor_links_to_zha_device_without_claiming_it(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_zha_device,
    gateway_proxy: GatewayProxyState,
):
    device_entry = make_zha_device(IEEE)
    gateway_proxy.ready_with(IEEE_OBJ, available=True)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entity_id = entity_registry.async_get_entity_id(
        "binary_sensor", DOMAIN, _unique_id(IEEE_OBJ)
    )
    reg_entry = entity_registry.async_get(entity_id)
    assert reg_entry.device_id == device_entry.id

    # The actual regression guard: our config entry must not become an
    # owner of ZHA's device (the "(Helper)" misclassification bug).
    linked_device = dr.async_get(hass).async_get(device_entry.id)
    assert config_entry.entry_id not in linked_device.config_entries


async def test_pairing_race_skips_device_not_yet_registered(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    zha_config_entry: MockConfigEntry,
    gateway_proxy: GatewayProxyState,
):
    # Deliberately not calling make_zha_device -- the device isn't in the
    # registry yet, as if ZHA reported it before finishing registration.
    gateway_proxy.ready_with(IEEE_OBJ, available=True)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, _unique_id(IEEE_OBJ)
    )
    assert entity_id is None
