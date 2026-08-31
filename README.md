# Tuya‑LAN for Home Assistant

A **fully local, cloud‑free** custom integration for Tuya / Smart Life Wi‑Fi devices.

* No Tuya IoT Platform account.
* No Smart Life / Tuya app running in the background.
* No `tuya-convert` or firmware flashing required (but supported as a key source).
* Everything happens on your LAN.

The integration can:

| Capability | Where |
|---|---|
| **Discover devices that are not added yet** by listening to Tuya's UDP broadcasts (ports 6666 / 6667 / 6699) | `discovery.py` |
| **Guide you through setup** with a config flow: pick a discovered device, paste its local key, choose a *profile* | `config_flow.py` |
| **Talk to devices locally** with protocol versions 3.1 – 3.5 (AES‑ECB and AES‑GCM, session negotiation) | `protocol/` |
| **Explore unknown devices** — dump every data point (DP), its type and live value, so you can build a profile | `services.yaml` → `tuya_lan.dump_dps`, plus device diagnostics |
| **Extend without touching Python** — device *profiles* are YAML files that map DPs to entities (switch, light, sensor, number, select, …) | `profiles/` |
| **Add custom handlers** — raw DP read/write services and a `tuya_lan_dp` event bus for automations | `services.yaml`, `coordinator.py` |

## Why "fully offline"

Tuya's local protocol encrypts traffic with a per‑device **local key**. That key is
normally handed out by Tuya's cloud when the device is paired. This integration
never contacts the cloud, so **you supply the key yourself**. Accepted sources:

1. A key you already extracted (e.g. from a previous `tinytuya` / LocalTuya setup,
   from a router/app packet capture during pairing, or from `cloudcutter`).
2. A rooted‑app / ADB backup of the Smart Life app (`data/`),
   from which the bundled `tools/tuya_lan_probe.py --extract-keys` can read the cache.
3. Devices in AP/pairing mode that still use the well‑known default key
   (older firmware) — auto‑tried during discovery.

See [`docs/getting-keys.md`](docs/getting-keys.md) for the detailed, legal, on‑device methods.

## Install

### HACS (custom repository)

1. HACS → ⋮ → *Custom repositories* → add this repo, category **Integration**.
2. Install **Tuya‑LAN**, restart Home Assistant.
3. *Settings → Devices & Services → Add Integration → Tuya‑LAN*.

### Manual

Copy `custom_components/tuya_lan` into your HA `config/custom_components/` and restart.

## Quick start

1. Add the integration. It shows every device it heard on the LAN that is **not
   already configured**.
2. Pick one. Paste its **local key** (22‑char base64‑ish string).
3. Choose a **profile**:
   * a bundled one that matches (`generic_switch`, `generic_plug_energy`, …), or
   * **Detect** — the integration connects, dumps the DPs and proposes entities, or
   * **Raw** — no entities, just the `tuya_lan.set_dp` service and `tuya_lan_dp` events.
4. Done. Entities appear under the new device.

## Writing a profile

Profiles live in `custom_components/tuya_lan/profiles/*.yaml` and, for user
overrides, in `config/tuya_lan/profiles/*.yaml` (created on first run). Example:

```yaml
id: my_dehumidifier
name: Acme Dehumidifier XYZ
match:                     # optional auto-match hints
  product_key: keqdwerij23
  dps: [1, 2, 4, 12]
primary_entity:
  platform: humidifier
  dps:
    switch: "1"
    current_humidity: "6"
    target_humidity: "2"
    mode: "4"
  device_class: dehumidifier
  modes: { auto: "0", low: "1", high: "2" }
secondary_entities:
  - platform: sensor
    name: Tank
    dps: { sensor: "5" }
    device_class: null
    icon: mdi:cup-water
  - platform: binary_sensor
    name: Tank full
    dps: { sensor: "12" }
    device_class: problem
```

Reload with the `tuya_lan.reload_profiles` service — no restart.

## Development

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements-dev.txt
pytest
```

`tools/tuya_lan_probe.py` is a standalone CLI (no Home Assistant needed) for
discovery, key testing and DP dumping.

## License

Apache‑2.0. Protocol implementation is a clean‑room async re‑implementation
informed by the public documentation of the Tuya local protocol and the
Apache‑2.0 `tinytuya` / `localtuya` projects.
