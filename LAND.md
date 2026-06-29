# LAND — Multi-Model Review Verdict (v0.3.0 → v0.5.5)

> Status (landed in 0.5.6): ACT-ON items A1–A8 done, plus the cheap
> CONSIDER items "value coercion in `_device_is_valid`" and "`unique_id`
> None guard".
>
> Status (landed in 0.5.7): second-pass review fixes — temp getters
> float-coerced, `device`/`energy_usage` made KeyError-safe, `current_heat_mode`
> int-coerced, energy coordinator all-invalid first-refresh guard,
> `supported_features` derived from the vendor mode set (no flapping).
>
> Status (landed in 0.5.8): the second-pass CRITICAL (Opus C1 — water_heater
> `capability_attributes`/`supported_features` are read unconditionally and hit
> `self.device`) is resolved by the 0.5.7 cached-snapshot `device` fallback;
> plus the bitmap decoder now decodes unexpected lengths instead of discarding
> them (+ whitespace strip), and a malformed per-device payload skips only that
> device.
>
> Still open (DEFERRED / queued): HA-harness entity+coordinator tests
> (partial-skip water_heater regression test would have caught C1 — highest
> priority follow-up), writable-vs-readable property verification (needs
> hardware), `_post_datapoint` non-JSON 200 handling, a stub-vs-real enum
> drift-guard test, and the energy-coordinator naive `datetime` (pre-existing).

Synthesis of an adversarial multi-model code review of the recent fork arc
(`e3bc966..HEAD`): write platforms (`button`/`number`/`switch`/`text`), the
`fault_codes` decoder, coordinator hardening (60s timeout + per-device skip),
the described-entity mixin, removal of the cosmetic clear/reset buttons with
registry cleanup, the actual-vs-requested heat-mode change, and the new pytest
suite + CI job.

## Reviewers

- GPT-5.5 (medium) — completed
- Gemini 3.5 Flash — completed
- Claude 4.6 Sonnet (max thinking) — completed
- Claude Opus 4.8 (thinking max) — completed; cross-checked against the real
  upstream `bradford_white_connect_client` v0.0.21 source
- GPT-5.3 Codex (xhigh) — did not emit structured findings (ended after its
  diagnostics pass); its interim notes matched the consensus high-risk flags

Verdict in one line: **the architecture is good, but the `_device_is_valid`
"skip a device" change shipped without its required companion (an `available`
guard), which is a real regression. Fix that before anything else.**

---

## ACT ON (clear bugs / strong consensus)

### A1 — `available` guard for skipped devices  ·  CRITICAL  ·  4/5 reviewers
`coordinator._async_update_data` now omits an invalid DSN from the returned
dict, but `BradfordWhiteConnectStatusEntity.device` does
`self.coordinator.data[self._dsn]` and `available` only follows
`last_update_success`. A skipped device therefore stays **available** while
every `self.device` access raises `KeyError`:
- `sensor.py` swallows it (`except (... KeyError ...)`) → silent `Unknown`.
- `binary_sensor` / `switch` / `number` / `text` / `water_heater` do **not** →
  repeated `ERROR` log storms every cycle; write service calls surface a raw
  `KeyError: '{dsn}'` to the user.

This is strictly worse than the old `raise UpdateFailed` (which cleanly marked
everything unavailable). Fix on `BradfordWhiteConnectStatusEntity`:

```python
@property
def available(self) -> bool:
    return super().available and self._dsn in self.coordinator.data
```

Also guard `device` (return via `.get`) and prefer keeping last-known-good data
for a skipped cycle.

### A2 — All-invalid first refresh loads zero entities with no retry  ·  CRITICAL  ·  Opus (related to A1)
An all-invalid first refresh returns `{}`, which is a *successful* update, so
`async_config_entry_first_refresh()` does not raise `ConfigEntryNotReady`. The
entry loads with no devices/entities and no auto-retry — even on a single
heater. Treat "all devices invalid on first refresh" as `UpdateFailed` so the
`ConfigEntryNotReady` backoff self-heals.

### A3 — 60s timeout is a shared budget across the whole device loop  ·  WARNING→CRITICAL  ·  4/5 reviewers
One `asyncio.timeout(60)` wraps `get_devices()` + every per-device
`get_device_properties()` (and the energy coordinator's per-device energy
calls). On a multi-heater account one slow cloud response starves the rest and
fails the entire refresh. Also: a single per-device exception currently
propagates and fails the whole account, defeating the skip design. Fix:
per-call/per-device timeout **and** wrap each per-device call in
`try/except (BradfordWhiteConnectUnknownException, aiohttp.ClientError, TimeoutError)`
→ log + `continue`.

### A4 — `current_operation` can fall outside `operation_list`  ·  WARNING  ·  4/5 reviewers
`operation_list` falls back to `[STATE_OFF]` when the model is unknown
(`_supported_vendor_modes()` empty), but `current_operation` independently maps
live `current_heat_mode`. HA's water-heater contract expects
`current_operation ∈ operation_list`. Include the current mapped mode in
`operation_list`, or don't fabricate `[STATE_OFF]` when the live mode is known.
(Gemini also notes the unknown-model path makes `async_turn_away_mode_off`
raise `HomeAssistantError` and locks mode changes — fall back to a default mode
set for unrecognized models.)

### A5 — Test stub always shadows the real client (and the enum is off-by-one)  ·  WARNING  ·  3-4/5 reviewers
`conftest._install_upstream_client_stub()` registers the stub into
`sys.modules` at import time, so it wins **even in CI** where the real client is
installed — the docstring's "the real client is used in CI" claim is false. The
stub's `BradfordWhiteConnectHeatingModes` is `HYBRID=1..VACATION=5`, but the
real upstream is `0..4` (verified by Opus). Production imports the real enum so
the shipped mapping is correct, but the tests build `HEAT_MODE_NAMES` from the
stub and would never catch real enum drift. Fix: only stub when the real
package is genuinely absent (try/except import), and add a guard test asserting
stub == real when the client is installed.

### A6 — `.venv-test/` committed to git, wrong Python  ·  NIT (but unanimous)  ·  4/5 reviewers
14 tracked files under `.venv-test/` with absolute, machine-local symlinks;
`pyvenv.cfg` pins `3.9.6` while the Pipfile/CI/`asyncio.timeout` all require
3.11 (`asyncio.timeout` doesn't exist on 3.9). `.gitignore` only matches
`.venv`. Fix: `git rm -r --cached .venv-test/` and add `.venv-test/` to
`.gitignore`.

### A7 — Alarm bitmap: no length/charset validation + inconsistent numbering  ·  WARNING/NIT  ·  4/5 reviewers
`decode_alarm_bitmap` iterates any-length input and ignores non-`1` chars, so an
overlong/garbled cloud value invents phantom `F41+` faults and a non-string
value silently yields `OK`. Validate `len == 40` and charset `{0,1}` (log once
on violation). Also the numbering is internally inconsistent: `tentative_code`
is 1-based (`F{index+1}`) but the unknown label is 0-based
(`Unknown fault (bit {index})`) → a record can read `F2 / "Unknown fault (bit 1)"`.
Pick one base.

### A8 — INFO log leaks `heater_name` value + DSN  ·  WARNING  ·  2/5 reviewers
`_LOGGER.info("Writing %s=%r to device %s", name, payload_value, device.dsn)`
echoes user free-text (`heater_name`) and the device serial at INFO (default
logs), contradicting this PR's own README PII-redaction note. Drop to DEBUG,
omit the DSN, and don't echo free-text values.

---

## CONSIDER (worth doing; lower consensus or needs verification)

- **Writable vs readable property names (Opus W5).** The generic writer POSTs to
  `/properties/{name}/datapoints.json` using the *readable* property name, but
  the upstream client itself writes different input names (`water_setpoint_in`
  not `_out`; `set_heat_mode_*` not `current_heat_mode`). The new write entities
  (`controller_reboot`, `wifi_reboot`, `set_vacation_mode_days`,
  `set_electric_mode_days`, `set_heat_timer_1/4`, `drm_advanced_loadup`,
  `drm_service`, `heater_name`) assume read-name == write-input-name. Verify each
  against the `Property` `direction`/`read_only` flags (already fetched) and/or
  hardware; gate write entities on a writable-input check, not mere presence.
- **`_post_datapoint` non-JSON 200 (Opus N5).** If `http_post_request` calls
  `response.json()`, a reboot returning an empty/non-JSON 200 raises
  `ContentTypeError` → a successful write surfaces as a failure. Confirm and
  handle.
- **`unique_id` None guard (Sonnet W4).** `entity.unique_id.endswith(...)` in
  `_async_cleanup_removed_buttons` raises `AttributeError` if `unique_id` is
  None, aborting the whole cleanup loop. Guard with `entity.unique_id and ...`.
- **String-valued telemetry coercion (Gemini #5).** `_device_is_valid` does
  `value < 0 or value > 200` directly; a stringified number from the cloud
  raises `TypeError` and fails the refresh. Coerce to float with try/except.
- **Energy coordinator naive datetime (Sonnet W5, Opus N8 — pre-existing).**
  `usage_date = datetime.datetime.now()` is naive; day-bucket boundaries drift
  off-UTC. Make it `datetime.now(timezone.utc)` for consistency.

---

## NOTED (acceptable today; document or guard for later)

- `current_heat_mode` sensor now emits enum strings where it previously emitted
  raw ints → history/long-term-statistics discontinuity on upgrade. Add a
  release note (Opus N6).
- `_async_cleanup_removed_buttons` runs on every setup and matches by
  `endswith((...))`; a future legit entity ending in `_reset_filter` /
  `_clear_alarm_counts` would be silently deleted. Consider a one-time migration
  guard (Opus N7).
- URL built via `str.format` with an unescaped path segment — safe while `name`
  is constant, latent if it ever becomes dynamic; prefer `yarl.URL` /
  percent-encoding (Opus N4).
- `conftest` prepends the integration dir to `sys.path`, giving its modules
  priority over stdlib/installed packages (`sensor.py` could shadow). Scoped
  imports would be cleaner (Sonnet N6).

---

## DISMISSED (reviewers checked; clean)

- **Coordinator re-entrancy / deadlock** — `async_set_property → async_request_refresh`
  is only called from entity command handlers, never inside `_async_update_data`;
  `async_request_refresh` is debounced. No recursion/deadlock. (Opus + GPT-5.5)
- **Timezone subtraction in `_refresh_update_interval`** — all five
  `last_api_set_datetime` write sites use `datetime.now(timezone.utc)` and the
  consumer subtracts a tz-aware now. No naive/aware mix. (all)
- **`_post_datapoint` payload encoding** — `isinstance(value, bool)` is checked
  before the int passthrough (bool is an int subclass), matching Ayla's 1/0
  convention; body goes through `json.dumps` so free-text can't inject. (Opus)
- **Registry cleanup scoping/idempotency** — correctly limited to
  `async_entries_for_config_entry`, `str.endswith(tuple)` is valid, idempotent
  on re-runs. (Sonnet, Opus, GPT-5.5)
- **ENUM sensor `None` handling** — `heat_mode_to_name` returns only mapped
  values or `None`; for kept devices `is_valid` ⟺ mapped key set, so no
  out-of-options state. (Opus, Sonnet)

---

## Suggested landing order

1. A1 + A2 + A3 together (the coordinator/entity availability + isolation fix —
   this is the actual regression).
2. A4 (operation_list contract) and A8 (log level/PII).
3. A5 + A6 (test/CI hygiene so the suite actually exercises the real client).
4. A7 (bitmap robustness).
5. Triage CONSIDER items — A-list W5 (write-name verification) likely needs
   hardware before any write entity can be trusted in a release.
