"""Shared fixtures for the functional test suite.

Fakes stand in only for ZHA's own data (a device/gateway shape), never for
HA's own device/entity registries or config-entry machinery; those are
exercised for real via pytest-homeassistant-custom-component. See
../test_zha_contract.py for the independent check that these fakes'
shape still matches ZHA's real classes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zha_connectivity_sensor import DOMAIN
from custom_components.zha_connectivity_sensor.binary_sensor import _unique_id
from custom_components.zha_connectivity_sensor.helpers import ZHA_DOMAIN

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let hass load custom_components/zha_connectivity_sensor in every test."""


@dataclass
class FakeDevice:
    """Stand-in for zha.zigbee.device.Device (only the attributes read)."""

    ieee: Any
    available: bool | None = True
    last_seen: float | None = None


@dataclass
class FakeGateway:
    """Stand-in for zha.application.gateway.Gateway (only .devices)."""

    devices: dict[Any, FakeDevice] = field(default_factory=dict)


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """A config entry for this integration itself."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def zha_config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Stand-in for ZHA itself being a configured integration."""
    entry = MockConfigEntry(domain=ZHA_DOMAIN, data={})
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def make_zha_device(device_registry: dr.DeviceRegistry, zha_config_entry: MockConfigEntry):
    """Factory: register a real, ZHA-owned device in the device registry."""

    def _make(ieee: str):
        return device_registry.async_get_or_create(
            config_entry_id=zha_config_entry.entry_id,
            identifiers={(ZHA_DOMAIN, ieee)},
        )

    return _make


@pytest.fixture
def seed_known_sensor(entity_registry: er.EntityRegistry, config_entry: MockConfigEntry):
    """Factory: seed a prior-run entity registry entry for a device.

    Represents "this sensor already existed from a previous setup":
    what makes __init__.py's has_known_devices check true (a restart with
    history), as opposed to a genuine first-ever setup (Area E).
    """

    def _seed(device_entry, ieee_obj):
        return entity_registry.async_get_or_create(
            domain="binary_sensor",
            platform=DOMAIN,
            unique_id=_unique_id(ieee_obj),
            config_entry=config_entry,
            device_id=device_entry.id,
        )

    return _seed


class GatewayProxyState:
    """Mutable per-test control for the patched get_zha_gateway_proxy.

    Starts not-ready (raises ValueError, matching ZHA's real behaviour
    before its gateway exists). Call `.ready(gateway)` to simulate ZHA
    having (re)connected, or `.not_ready()` to simulate it going away
    again.
    """

    def __init__(self, config_entry: MockConfigEntry) -> None:
        self.config_entry = config_entry
        self.gateway: FakeGateway | None = None
        self._raise = True

    def ready(self, gateway: FakeGateway) -> None:
        self._raise = False
        self.gateway = gateway

    def ready_with(self, ieee_obj: Any, **device_kwargs: Any) -> FakeGateway:
        """Convenience: mark ready with a gateway containing one device."""
        gateway = FakeGateway(devices={ieee_obj: FakeDevice(ieee_obj, **device_kwargs)})
        self.ready(gateway)
        return gateway

    def not_ready(self) -> None:
        self._raise = True
        self.gateway = None


@pytest.fixture
def gateway_proxy(zha_config_entry: MockConfigEntry):
    """Patch helpers.get_zha_gateway_proxy: the one real HA-boundary call
    that get_zha_gateway_and_entry wraps. Patching here flows through to
    __init__.py/coordinator.py/binary_sensor.py automatically, since they
    all call the same unpatched get_zha_gateway_and_entry function object.
    """
    state = GatewayProxyState(zha_config_entry)

    def _get_zha_gateway_proxy(hass):
        if state._raise:
            raise ValueError("ZHA gateway not ready")
        return SimpleNamespace(gateway=state.gateway, config_entry=state.config_entry)

    with patch(
        "custom_components.zha_connectivity_sensor.helpers.get_zha_gateway_proxy",
        side_effect=_get_zha_gateway_proxy,
    ):
        yield state
