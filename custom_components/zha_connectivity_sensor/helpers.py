"""Shared helpers for resolving the ZHA gateway."""

from __future__ import annotations

from typing import Any

from homeassistant.components.zha.helpers import get_zha_gateway_proxy
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

ZHA_DOMAIN = "zha"
DEFAULT_ENABLE_NEW_DEVICES = False


def get_enable_new_devices(config_entry: ConfigEntry) -> bool:
    """Return the resolved enable_new_devices option value."""
    return config_entry.options.get(
        "enable_new_devices",
        config_entry.data.get("enable_new_devices", DEFAULT_ENABLE_NEW_DEVICES),
    )


def zha_identifier(ieee_obj: Any) -> tuple[str, str]:
    """Return the device registry identifier tuple for an IEEE address."""
    return (ZHA_DOMAIN, str(ieee_obj))


def ieee_from_device_entry(device_entry: DeviceEntry) -> str | None:
    """Extract the IEEE string from a ZHA device entry's identifiers."""
    return next(
        (value for domain, value in device_entry.identifiers if domain == ZHA_DOMAIN),
        None,
    )


def get_zha_gateway_and_entry(
    hass: HomeAssistant,
) -> tuple[Any, ConfigEntry] | tuple[None, None]:
    """Return (gateway, owning ZHA config entry), or (None, None) if not ready."""
    try:
        gateway_proxy = get_zha_gateway_proxy(hass)
    except ValueError:
        return None, None
    return gateway_proxy.gateway, gateway_proxy.config_entry
