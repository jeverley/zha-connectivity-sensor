from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from . import DOMAIN
from .helpers import DEFAULT_ENABLE_NEW_DEVICES, ZHA_DOMAIN, get_enable_new_devices


class ZHAConnectivitySensorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ZHA Connectivity Sensor."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step when added via the UI."""
        # single_config_entry in manifest.json already blocks a second
        # instance before this step runs -- no need to check here too.
        # Existence check, not readiness -- ZHA being unloaded right now is
        # fine, we just need it configured at all.
        if not self.hass.config_entries.async_entries(ZHA_DOMAIN):
            return self.async_abort(reason="zha_not_configured")

        if user_input is not None:
            return self.async_create_entry(title="ZHA Connectivity Sensor", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "enable_new_devices", default=DEFAULT_ENABLE_NEW_DEVICES
                    ): bool,
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ZHAConnectivitySensorOptionsFlow()


class ZHAConnectivitySensorOptionsFlow(config_entries.OptionsFlow):
    """Handle options for ZHA Connectivity Sensor."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        enable_new_devices = get_enable_new_devices(self.config_entry)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("enable_new_devices", default=enable_new_devices): bool,
                }
            ),
        )
