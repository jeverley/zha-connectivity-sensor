"""Contract test: guards against ZHA's internal API changing underneath us.

Not a test of our own code -- this only asserts that the private ZHA/zha
internals we rely on (undocumented, not a public API) still look the way
we expect. A failure here means an upstream ZHA change, not a bug in this
integration.
"""

from __future__ import annotations

import inspect

from homeassistant.components.zha.helpers import (
    SIGNAL_ADD_ENTITIES,
    get_zha_gateway_proxy,
)
from zha.application.gateway import Gateway
from zha.zigbee.device import Device


def test_signal_add_entities_unchanged() -> None:
    """SIGNAL_ADD_ENTITIES is the dispatcher signal we listen for new devices on."""
    assert SIGNAL_ADD_ENTITIES == "zha_add_entities"


def test_get_zha_gateway_proxy_importable() -> None:
    """get_zha_gateway_proxy must still exist and be callable."""
    assert callable(get_zha_gateway_proxy)


def test_device_exposes_available_and_last_seen() -> None:
    """Device.available and Device.last_seen must still exist as properties."""
    assert isinstance(inspect.getattr_static(Device, "available"), property)
    assert isinstance(inspect.getattr_static(Device, "last_seen"), property)


def test_gateway_exposes_devices() -> None:
    """Gateway.devices must still exist as a property."""
    assert isinstance(inspect.getattr_static(Gateway, "devices"), property)
