# :factory: Home Assistant integration — plan

Status: **proposal**, nothing implemented yet. This document is meant to be discussed in the PR before any code is written.

## TL;DR

- Goal: let people who already run `wanhao-d12-230-cli-monitor serve` see their printer in Home Assistant (HA) with as little effort as possible, using the existing `GET /status` REST endpoint.
- **Phase 1 (zero code, ships first):** a ready-to-copy HA *package* YAML file (`homeassistant/wanhao_d12.yaml`) built on HA's built-in [`rest:` integration](https://www.home-assistant.io/integrations/rest/). One HTTP request per poll feeds every sensor. Users drop the file into `config/packages/`, change the URL, restart HA.
- **Phase 2 (small server changes):** add `age_seconds` (and `server_version`) to `/status` so HA can detect a stale/dead poller without depending on clock sync between the Pi and the HA host.
- **Phase 3 (real "plugin"):** a custom integration `wanhao_d12` installable through [HACS](https://www.hacs.xyz/) as a *custom repository*, with a UI config flow (host + port), one HA device and typed entities, built on the standard `DataUpdateCoordinator` pattern.
- Phase 3 lives in a **separate GitHub repository** (recommended): HACS allows one integration per repo and wants `hacs.json`, `brand/` and its own release tags, and the HA test stack has its own Python version constraints.
- Out of scope for now: printer *control* (the API is read-only), zeroconf discovery, authentication.
- README.md and CLAUDE.md get a pointer to this plan now, and a proper "Home Assistant" section when Phase 1 lands.

## Context: what the API gives us

`GET /status` (see `printer_monitor/server.py`) returns:

| Field | Type | HA mapping idea |
|-------|------|-----------------|
| `connected` | bool | `binary_sensor`, device class `connectivity` |
| `last_update` | float (epoch, Pi clock) | staleness check (see Phase 2) |
| `last_error` | str | `sensor`, entity category `diagnostic` |
| `hotend0` / `hotend1` / `bed` → `current`, `target` | float °C | `sensor`, device class `temperature`, `°C`, state class `measurement` |
| `hotend0` / `hotend1` / `bed` → `power` | int, raw PWM 0–127 | `sensor`, `%` = `power / 127 * 100` |
| `sd_printing` | bool | `binary_sensor`, device class `running` |
| `sd_progress` | float % | `sensor`, `%`, state class `measurement` |
| `sd_bytes_done` / `sd_bytes_total` | int | attributes of the progress sensor (or diagnostic sensors) |
| `x`, `y`, `z`, `e` | float mm | diagnostic sensors, disabled by default (noisy) |
| `feedrate_percent` | int | `sensor`, `%` |

Constraints to keep in mind:

- The server binds `0.0.0.0` with **no authentication**. HA must reach it on the LAN (e.g. `http://pi:8111/status` with the documented systemd unit, `8000` by default).
- The server polls the printer every 2.5 s; HA polling every 10–30 s is plenty and costs nothing on the serial side (HA only reads the cached `PrinterState`).
- `connected: false` means "the printer is off / unplugged / silent", not "the monitor is down". The monitor being down shows up as an HTTP error. Both cases need distinct handling in HA.

## Phase 1 — HA package YAML (no code)

Deliverable: `homeassistant/wanhao_d12.yaml` in this repo + a README section.

Why this first: HA's `rest:` integration (top-level form) issues **one** request per `scan_interval` and fans the JSON out to several `sensor` / `binary_sensor` entities. All the keys we need are documented on the [RESTful Sensor](https://www.home-assistant.io/integrations/sensor.rest/) page: `unique_id`, `device_class`, `state_class`, `unit_of_measurement`, `value_template`, `availability`, `json_attributes`. It works on every HA install type, needs no HACS, and doubles as a reference for Phase 3.

Sketch (to be validated against a real HA instance before merging):

```yaml
# config/packages/wanhao_d12.yaml
# Enable packages once in configuration.yaml:
#   homeassistant:
#     packages: !include_dir_named packages
rest:
  - resource: http://pi:8111/status   # <- change me
    scan_interval: 15
    timeout: 5
    sensor:
      - name: "Wanhao hotend 0 temperature"
        unique_id: wanhao_d12_hotend0_temp
        value_template: "{{ value_json.hotend0.current }}"
        device_class: temperature
        unit_of_measurement: "°C"
        state_class: measurement
        availability: "{{ value_json.connected }}"
      - name: "Wanhao hotend 0 target"
        unique_id: wanhao_d12_hotend0_target
        value_template: "{{ value_json.hotend0.target }}"
        device_class: temperature
        unit_of_measurement: "°C"
        availability: "{{ value_json.connected }}"
      - name: "Wanhao hotend 0 power"
        unique_id: wanhao_d12_hotend0_power
        value_template: "{{ (value_json.hotend0.power / 127 * 100) | round(0) }}"
        unit_of_measurement: "%"
        state_class: measurement
        availability: "{{ value_json.connected }}"
      # ... same for hotend1 and bed ...
      - name: "Wanhao print progress"
        unique_id: wanhao_d12_progress
        value_template: "{{ value_json.sd_progress | round(1) }}"
        unit_of_measurement: "%"
        state_class: measurement
        json_attributes:
          - sd_bytes_done
          - sd_bytes_total
        availability: "{{ value_json.connected }}"
      - name: "Wanhao feedrate"
        unique_id: wanhao_d12_feedrate
        value_template: "{{ value_json.feedrate_percent }}"
        unit_of_measurement: "%"
        availability: "{{ value_json.connected }}"
      - name: "Wanhao last error"
        unique_id: wanhao_d12_last_error
        value_template: "{{ value_json.last_error or 'none' }}"
    binary_sensor:
      - name: "Wanhao connected"
        unique_id: wanhao_d12_connected
        value_template: "{{ value_json.connected }}"
        device_class: connectivity
      - name: "Wanhao printing"
        unique_id: wanhao_d12_printing
        value_template: "{{ value_json.sd_printing }}"
        device_class: running
        availability: "{{ value_json.connected }}"
```

Points to verify while implementing Phase 1:

- [ ] `availability` templates can read `value_json` in the `rest:` integration on current HA (if not, fall back to `value_template` returning `none` when disconnected).
- [ ] `hotend1` is meaningful on the user's D12 230 variant; if not, ship it commented out.
- [ ] Optional: an example Lovelace card (tile/gauge cards for temperatures, progress bar) and an example automation ("print finished" = `binary_sensor.wanhao_printing` goes `on` → `off` while `connected` stays `on`, then send a notification).
- [ ] Unique IDs are hard-coded, so a second printer needs a find-and-replace; document it.

Limits of Phase 1: no device grouping in the UI, YAML-only configuration, staleness detection relies on Phase 2.

## Phase 2 — small server-side additions

Small, backwards-compatible changes to `printer_monitor/server.py` that make any client (YAML or custom integration) more robust:

1. **`age_seconds`** = `time() - state.last_update`, computed on the Pi. The CLAUDE.md failure mode "stale `last_update` with `connected: true`" (dead poller thread) can then be detected in HA with `availability: "{{ value_json.connected and value_json.age_seconds < 30 }}"`, without comparing two different clocks.
2. **`server_version`** (package version) so the integration can warn on incompatible servers.
3. Optional: **`GET /health`** returning `200` when the poller thread is alive, `503` otherwise, for HA's binary sensor or for uptime monitors.
4. Optional: a stable **printer identifier** (e.g. the `/dev/serial/by-id` name or a `--name` option) usable as the HA device unique ID.

Each item comes with unit tests in `tests/` (FastAPI `TestClient`) and an update of the README "REST API Server" section.

## Phase 3 — custom integration via HACS

### Where

New public GitHub repo, e.g. `wixyvir/ha-wanhao-d12-230` (name to be decided). Reasons:

- HACS manages **one integration per repository**, expects `custom_components/<domain>/`, a root `hacs.json` (only `name` is required) and a `brand/icon.png` ([HACS publishing docs](https://www.hacs.xyz/docs/publish/integration/)).
- HACS uses GitHub releases/tags for versions; mixing them with this package's PyPI/poetry versions would be confusing.
- HA core and `pytest-homeassistant-custom-component` pin recent Python versions, while this project's CI runs 3.10–3.13.

Users install it through HACS → ⋮ → *Custom repositories* → paste the repo URL, type *Integration* ([HACS FAQ](https://www.hacs.xyz/docs/faq/custom_repositories/)). Submitting to the HACS default store can come later.

### Layout

```
custom_components/wanhao_d12/
├── __init__.py        # async_setup_entry / async_unload_entry, entry.runtime_data = coordinator
├── manifest.json      # domain, name, version, documentation, issue_tracker, codeowners,
│                      # config_flow: true, iot_class: local_polling, integration_type: device
├── config_flow.py     # host + port (default 8111), validates by calling GET /status
├── const.py
├── coordinator.py     # DataUpdateCoordinator, update_interval option (default 15 s)
├── entity.py          # base CoordinatorEntity with DeviceInfo (manufacturer Wanhao, model D12 230)
├── sensor.py          # SensorEntityDescription list mirroring the Phase 1 table
├── binary_sensor.py   # connected, printing
├── diagnostics.py     # dumps the last /status payload
├── strings.json
└── translations/en.json
hacs.json
brand/icon.png
tests/                 # pytest-homeassistant-custom-component
.github/workflows/     # hassfest + HACS validation actions + pytest
```

### Behaviour

Follows HA's [fetching data guide](https://contributors.home-assistant.io/core/integrations/fetching-data/):

- `coordinator._async_update_data()` uses HA's shared `aiohttp` session (`async_get_clientsession`) to `GET /status`; HTTP/timeout/JSON errors raise `UpdateFailed` → all entities become unavailable (the **monitor** is down).
- `async_config_entry_first_refresh()` in `async_setup_entry`, so a monitor that is down at HA startup gives `ConfigEntryNotReady` and HA retries.
- When the monitor answers but `connected` is `false` (or `age_seconds` too high, Phase 2), only the `connected` binary sensor stays available (`off`); printer entities report unavailable. Implemented in the base entity's `available` property.
- No external Python dependency (`requirements: []`): the API is a single JSON GET, so no client library on PyPI is needed.
- Device unique ID: `host:port` until Phase 2 item 4 provides a stable printer identifier.
- Positions `x/y/z/e` are `EntityCategory.DIAGNOSTIC` and disabled by default.

### Quality checks

- `hassfest` and the HACS validation GitHub Actions on every push.
- Tests: config flow (success, cannot connect, already configured), coordinator (OK, HTTP error, `connected: false`), entity values from a recorded `/status` fixture.
- Manual test against the Pi (`http://pi:8111`) on a test HA instance (Docker `homeassistant/home-assistant`).

## Out of scope / later

- **Printer control** (pause, set temperatures, upload): needs write endpoints in `server.py` and careful thinking about safety; nothing exists yet.
- **Zeroconf discovery**: the server could advertise `_wanhao-d12._tcp` and the integration could declare it in `manifest.json`; worth it only if several users ask.
- **Authentication**: the API has none; if added (token header), both phases need an option for it.
- **Time remaining**: the firmware only reports SD bytes, so an ETA would be an estimate from progress speed; could be a computed sensor later.

## Documentation updates

- Now (this PR): link this plan from README.md and CLAUDE.md.
- Phase 1: README "Home Assistant" section (enable packages, copy the file, change the URL, example card), CLAUDE.md mention of `homeassistant/`.
- Phase 2: README "REST API Server" field descriptions, CLAUDE.md conventions (`age_seconds` is server-computed).
- Phase 3: README of the new repo + a link from this README.

## Open questions

1. Separate repository for the HACS integration (recommended) or a `custom_components/` folder in this repo?
2. Integration domain / repo name (`wanhao_d12`? `wanhao_d12_230`?).
3. Is `hotend1` used on the target printer, or should it be hidden by default?
4. Should Phase 2 add a `--name` option for multi-printer setups now, or wait for a real need?
