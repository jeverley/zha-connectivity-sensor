# ZHA Connectivity Sensor

Adds a "Connectivity" binary sensor for devices on your
[ZHA](https://www.home-assistant.io/integrations/zha/) network, exposing
the internal ZHA connectivity state.

The sensor reports `connected` (on) when a device is reachable,
`disconnected` (off) when it isn't, matching the binary sensor
[connectivity device class](https://www.home-assistant.io/integrations/binary_sensor/#device-class).
While ZHA itself is starting up, reloading, or briefly unreachable, the
sensor reports "disconnected" rather than "unavailable".

Each sensor also carries a `last_seen` attribute showing when the device
was last seen.

Sensors are created for every device, including ones you pair later.
Whether a newly-paired device's sensor starts out enabled is configurable
(off by default).

A repair issue is raised under Settings -> Repairs if ZHA is unreachable
for more than 15 minutes.

## Requirements

- Home Assistant 2026.8+
- ZHA already configured

## Installing

**HACS:** search for "ZHA Connectivity Sensor", install, restart.

**Manual:** drop `custom_components/zha_connectivity_sensor` into your
`config/custom_components/` folder and restart.

## Setting it up

Add it from Settings -> Devices & Services -> Add Integration -> "ZHA
Connectivity Sensor". It won't show up until ZHA itself is set up, and
only one instance is needed since it covers every device automatically.

Devices present at setup always start enabled; the new-device option
controls anything paired afterwards, and can be changed later from the
integration's options.

## License

[MIT](LICENSE)
