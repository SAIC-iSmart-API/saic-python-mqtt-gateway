# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Branching strategy

- `main` — stable releases only
- `develop` — beta/integration branch; the default merge target for all feature and bugfix work

**Always branch from `develop` for features and bugfixes.** PRs must target `develop`, not `main`. The only exception is a hotfix that must go directly to `main`.

## Release process

1. Merge all relevant PRs into `develop`.
2. Add a `## <version>` section to `CHANGELOG.md` and commit it directly to `develop`.
3. Tag `develop` as `<version>-rc<N>` (e.g. `0.13.0-rc1`) and push the tag — **RC tags live on `develop`, not `main`**.
4. After the RC is validated, open a PR from `develop` → `main` and merge it.
5. Tag the resulting `main` commit as the final release (e.g. `0.13.0`) and push the tag.

## Commands

```bash
# Install dependencies (first time or after lockfile changes)
poetry install --no-root

# Type check
poetry run mypy

# Lint (ruff runs with --fix --unsafe-fixes in pre-commit)
poetry run ruff check .
poetry run ruff format .

# Run all tests with coverage
poetry run pytest tests --cov

# Run a single test file or test
poetry run pytest tests/test_vehicle_info.py
poetry run pytest tests/test_vehicle_info.py::TestMg4UrbanRealBatteryCapacity::test_standard_range_43kwh -v
```

Pre-commit hooks run `ruff`, `ruff-format`, `mypy`, and `poetry-check` on every commit. Pytest runs as a **pre-push** hook. Always run mypy and ruff before committing to avoid fixup commits.

## Architecture

### Data flow

The gateway polls the SAIC cloud API on a per-vehicle schedule and bridges results to an MQTT broker. Incoming MQTT `/set` commands are forwarded back to the SAIC API.

```
SAIC Cloud API
    ↓  (VehicleState.should_refresh() controls timing)
VehicleHandler.__polling()
    ↓
VehicleState.handle_vehicle_status() → VehicleStatusRespPublisher → MQTT
VehicleState.handle_charge_status()  → ChrgMgmtDataRespPublisher  → MQTT
    ↓
extractors.extract_soc/range()  (cross-fuses BMS + vehicle status values)
    ↓
AbrpApi / OsmAndApi / OpenWBIntegration  (optional side-effects)

MQTT broker (/set topics)
    ↓
MqttGateway → VehicleHandler → VehicleCommandHandler → SAIC API
```

### Key modules

**`src/mqtt_gateway.py`** — top-level orchestrator. Implements `MqttCommandListener` (MQTT callbacks) and `VehicleHandlerLocator` (VIN → handler lookup).

**`src/vehicle.py` — `VehicleState`** — the polling state machine. Controls refresh timing via `PollingPhase` and `RefreshMode` enums. Exponential backoff on errors (doubles up to `refresh_period_inactive`). Polling is gated by `is_complete()` — all four refresh periods must be populated before the first poll. They are restored from retained MQTT messages on reconnect or defaulted by `configure_missing()` after a 10-second startup delay.

**`src/handlers/vehicle.py` — `VehicleHandler`** — per-VIN lifecycle. Owns `VehicleState`, `VehicleCommandHandler`, all integrations, and HA discovery. The `handle_vehicle()` coroutine is a long-lived asyncio task.

**`src/vehicle_info.py` — `VehicleInfo`** — static metadata derived from `VinInfo`. Holds series/model identity, vehicle configuration properties (e.g. `BType` for NMC/LFP battery type), battery capacity lookup, AC temperature mapping, and feature flags (`is_ev`, `has_sunroof`, etc.). `is_ev` is determined by series **not** starting with `"ZP22"`.

**`src/publisher/core.py` — `Publisher`** — abstract base with typed publish methods. Handles topic sanitization, data anonymization, and LWT. The `publish(key, Publishable)` dispatcher checks `bool` before `int` (Python's `isinstance(True, int)` is `True`).

**`src/handlers/command/`** — one `CommandHandlerBase` subclass per writable MQTT topic. All registered in `handlers/command/__init__.py::ALL_COMMAND_HANDLERS`.

**`src/status_publisher/`** — stateless publishers for each API response type. Return frozen dataclasses that carry extracted values back up to `VehicleState` for cross-cutting decisions (e.g. BMS vs vehicle SoC reconciliation).

**`src/extractors/__init__.py`** — pure functions that reconcile values present in both API responses. BMS values take precedence over vehicle status.

### Battery capacity (`src/vehicle_info.py`)

`real_battery_capacity` dispatches by `series` prefix to a vehicle-specific property. When adding a new model, add an `elif self.series.startswith(...)` branch and a corresponding `__<model>_real_battery_capacity` property. `supports_target_soc` (`BType == "1"`) distinguishes NMC from LFP where both share a series prefix. Custom capacity via `BATTERY_CAPACITY_MAPPING` (`VIN=kWh`) always overrides the lookup.

### Integrations (`src/integrations/`)

All optional, instantiated per-VIN:
- **Home Assistant**: MQTT auto-discovery. Re-published on broker reconnect or HA `online` LWT.
- **OpenWB**: subscribes to charger MQTT topics; triggers forced vehicle refresh on charge start; publishes SoC/range back to the charger.
- **ABRP / OsmAnd**: REST/HTTP telemetry push after each successful poll.

### MQTT topic structure

```
<prefix>/<saic_user>/vehicles/<vin>/<domain>/<key>        # status
<prefix>/<saic_user>/vehicles/<vin>/<domain>/<key>/set    # writable
<prefix>/<saic_user>/account/...                          # account-level
<prefix>/_internal/api/...                                # raw API debug
```

All topic constants are in `src/mqtt_topics.py`.
