# Autel MaxiCharger over HTTPS for Home Assistant

<img src="https://raw.githubusercontent.com/danwoodsy/autel-maxicharger-ha/main/custom_components/autel_http/brand/icon.png" alt="Autel MaxiCharger over HTTPS icon" width="128" height="128">

`autel-maxicharger-ha` provides local HTTPS control and sensors for Home Assistant.

Control an Autel MaxiCharger through its local `https://<charger>/localcfg`
interface. Start/stop and current-limit commands were verified on a single AC
charger, model **EW07-C050000A002**, firmware **V1.05.38**. Home Assistant
**2026.10 or newer** is required; the automated tests run against 2026.10.0.
Other firmware/models need validation against the same interface.

## Install through HACS

1. Open **HACS → ⋮ → Custom repositories**.
2. Add `https://github.com/danwoodsy/autel-maxicharger-ha` with type
   **Integration**.
3. Find **Autel MaxiCharger over HTTPS** in HACS and select **Download**.
4. Restart Home Assistant, then follow the configuration steps below.

## Manual installation

1. Copy `custom_components/autel_http` into your Home Assistant configuration
   directory, giving `/config/custom_components/autel_http/manifest.json`.
   The packaged ZIP contains this directory layout; extract it into `/config`.
2. Restart Home Assistant.

## Configure

1. Open **Settings → Devices & services → Add integration → Autel MaxiCharger over HTTPS**.
2. Enter the charger's **IP address or hostname**, **username** (usually `admin`),
   and **PIN Code** used by its local web page. Do not enter a token or hash.
3. Leave **Verify HTTPS certificate** off for the charger's self-signed certificate.
   Enable it if the charger uses a certificate trusted by Home Assistant.

The address accepts a hostname/IP, an HTTPS origin, or a nondefault port such as
`charger.local:8443`. Home Assistant must be able to reach the charger on your LAN.
Setup reads identity and settings; adding/reloading the integration does not
start, stop, or change the current limit. Serial/model/firmware are discovered.

The Home Assistant integration domain remains `autel_http`, so the project
rename preserves existing configuration entries and entity IDs.

Use the integration's **Reconfigure** menu to change the address, username, PIN,
or certificate setting. Leave the PIN blank there to retain the saved PIN.
Reconfiguration checks that the address still belongs to the same charger.

## Device page

The entities use Home Assistant's standard device page, with the simple layout
of the Sigenergy example:

| Section | Entities |
| --- | --- |
| Controls | **Start charging**, **Stop charging** buttons |
| Configuration | **Current limit**, a numeric input from 6–32 A in 1 A steps |
| Sensors | **Status**, **Charging**, **Vehicle connected**, **Charging power** (kW), **Charging current** (A), **Supply voltage** (V), **Session energy** (kWh), **Session duration**, **Meter energy** (kWh) |
| Diagnostic | **CPU usage**, **Memory usage**, **Flash usage** (%), **Wi-Fi signal quality**, **Network signal level** (0–4), **HTTP requests per minute**, **Autostart** (read-only), **Refresh**, download diagnostics |
| Diagnostic, initially disabled | Phase A/B/C current, pilot voltage/duty cycle |

The current limit is further capped by the discovered connector rating and
its reported offline-current ceiling. The device name, entity names, and area
can be changed using Home Assistant's usual controls. Enable additional
diagnostic entities on the device's entity page; this adds no polling requests.

CPU, memory, and flash usage come from realtime group `1536`, with percentage
units confirmed by the charger's frontend. Network signal is the reported
0–4 level, not a percentage or dBm measurement. These diagnostics use the
detailed refresh interval. Other group-1536 fields, including `OcppState` and
`LedBoardState`, are retained in downloaded diagnostics as raw codes. The
frontend describes OCPP state 0 as Normal; it does not establish a live OCPP
connection. Upgrading enables a network signal entity previously disabled by
the integration default while preserving explicit user disables.

**Wi-Fi signal quality** uses the charger's own frontend labels: **0 = Very poor,
1 = Weak, 2 = Fair, 3 = Good, 4 = Very good**. It reads the same cached network
response as the numeric signal sensor and makes no additional requests. Signal
quality is unknown for an unrecognized level or when the active network is not
Wi-Fi. The level does not identify the Wi-Fi band or give an exact dBm value.
The numeric **Network signal level** entity is preserved for existing automations.

The integration bundles its own charger/HTTPS icon in `brand/icon.png`, used
by Home Assistant's local brand-image support and included in the manual ZIP.

Pressing **Start charging** or **Stop charging** sends the verified command.
The service returns after its acknowledgement; slow status readback then runs
asynchronously. **Charging** reports actual charger state, so a car that is full
or declines charging can remain off after a successful start command.
**Vehicle connected** remains on when a plugged-in car is stopped.
Autostart is shown without changing the permission in the charger.
The hardware start/stop test was performed with Autostart enabled.

Unknown state codes are shown as unknown. Sensor failures mark readings
unavailable instead of fabricating zero power or a disconnected vehicle.
The charger can retain session energy after stopping and reset elapsed time;
these entities report its values. Energy counter resets across sessions and
reboots still need characterization, so the energy sensors do not yet enable
long-term energy statistics/Energy dashboard use. Power/current/voltage support
measurement statistics. Temperature is omitted because its raw scale is unverified.

## Refresh settings

Open the integration's **Configure** options:

Each field includes an explanation of the readings it refreshes and a suggested
starting value. All four settings use numeric inputs with seconds shown beside
the value.

After an update, restart Home Assistant fully and refresh your browser to load
the latest field labels and explanations. Home Assistant caches translations
while it is running.

| Option | Default | Allowed |
| --- | --- | --- |
| Whilst charging refresh interval | 10 seconds | 5–3,600 seconds; no slower than idle |
| Idle status refresh interval | 60 seconds | 15–3,600 seconds |
| Detailed refresh interval | 120 seconds | Idle interval–86,400 seconds |
| Timeout per HTTPS request | 15 seconds | 5–60 seconds |

Each normal refresh sends **two** requests: connector telemetry (`1537`, node 10)
and controller/connection status (`2560`, node 60). Group `1537` supplies charging
state, power, current, supply voltage, session energy, and elapsed time. Group
`2560` supplies the control-pilot state used to distinguish a stopped, plugged-in
vehicle from an unplugged one. Group `2561` supplies additional phase, pilot,
and meter readings, so it belongs on the slower detailed interval.

Polling automatically switches to the charging interval when `1537` reports
charging (`if_work_st: 2`), and to the idle interval for all other states. Set the
charging interval to **5, 10, or 15 seconds** as preferred; 10 seconds is the
default starting point for the small server. Existing saved status intervals
become the idle interval unchanged. An external start, such as from the Autel
app, is detected on the next idle poll. Home Assistant start/stop commands
request immediate status readback. A failed status poll backs off to the idle
interval until a successful poll establishes the charger state again.

When detailed polling is due, **five** more requests fetch configured current
(`parameter 5`), detailed meter/pilot/phase measurements (`2561`), Autostart
(`parameter 4`), network status, and CPU/memory/flash usage (`1536`). A current-limit
change requests immediate configured-current readback as well as status, without
refreshing unrelated diagnostics. Changes made in another app appear on the
next detailed poll or when you press **Refresh**.
Login and identity discovery run at setup; login also runs when authentication
is rejected. Wi-Fi scans and unrelated settings are not polled.

Requests run **one at a time**. A new normal interval starts after the previous
refresh finishes, so slow replies lengthen the effective interval and never
create overlapping polls. For example, a 5-second setting with two 2–3-second
responses gives about 9–11 seconds between normal refresh starts; a detailed
refresh takes longer. Detailed intervals are checked during normal polls;
they are approximate and can be longer than the selected interval. A pending
control gets a turn after the current HTTP request finishes. **Refresh** requests
a full refresh; repeated presses within one second are combined. Accepted
controls request a status refresh as well. Option changes reload the integration.

If an optional detail request fails, its entities become unavailable while the
normal charging sensors keep working. A failed detail request is retried on the
next detailed interval, or through the Refresh button.
Refresh stays available after a failed poll so you can request recovery. For
manual-only updates, turn off **Enable polling for updates** in the integration's
Home Assistant **System options**; setup and accepted controls still read status.

## Authentication and controls

The login sends SHA-256 of the PIN in `account_login`. The integration caches the
**charger-issued token** in memory, supplies it in the JSON body and raw
`Authorization` header, and logs in again once on an explicit JSON error `1001`.
The token is not assumed to be a PIN hash, and there is no periodic renewal.
Invalid credentials trigger Home Assistant's reauthentication flow.

Start/stop uses `debug_ctrl_pile_charge`, node 10, gun 1, with operation 1/2.
Current readback uses parameter 5, connector 1; changing it uses parameter 6,
connector 0, matching the verified web interface. A control requires both a
successful response and `ack: 0`. Controls are never automatically repeated
after a timeout or connection failure, because the charger may have applied
them already. Refresh the status before retrying an ambiguous result.

The integration uses HTTPS polling and needs no OCPP or WebSocket connection.
If OCPP or another controller is also connected, it may issue conflicting
start/stop or current-limit commands; coordinate your automations accordingly.

## First live check

1. Confirm the discovered model/firmware and current limit in Home Assistant.
2. With the vehicle plugged in, press **Start charging**. Wait for status
   readback and confirm **Charging** plus nonzero power/current and vehicle behavior.
3. Change the limit from 16 A to 10 A. Confirm configured readback and, after
   the vehicle reacts, measured current. Restore your chosen limit afterwards.
4. Press **Stop charging**. Confirm charging/power stop while
   **Vehicle connected** remains on.
5. Check availability and state over several normal and detailed refreshes.
   The cloud tests use sanitized captures; they cannot reach your LAN charger.

For troubleshooting, **Download diagnostics** uses cached measurements and makes
no extra charger requests. PIN, token, address, username, and serial are omitted.

## Request counter and debug logging

**HTTP requests per minute** counts this integration's outgoing HTTPS attempts
over the **last 60 seconds**. It includes login, authentication retries, reads,
controls, and failed attempts. Each attempt expires from the count after 60
seconds, so a burst of requests gradually drops out of the window. It is a
rolling count rather than a lifetime counter or a wall-clock minute reset.
Requests from the charger web UI, Autel app, and other integrations are not counted.

The counter is kept in memory and starts afresh when the integration reloads.
Home Assistant displays a cached reading, updated with status refreshes and by
a local 60-second timer. The timer makes **no charger requests**, works with
automatic polling disabled, and keeps the counter available during HTTP failures.
Downloaded diagnostics also include the counter and the last request's duration
in seconds. A manual **Refresh** itself makes seven requests, so expect a
temporary increase when troubleshooting.

Use **Settings → Devices & services → Autel MaxiCharger over HTTPS → ⋮ →
Enable debug logging** to collect a troubleshooting session. Reproduce the issue,
then disable debug logging and download the log when prompted. On Home Assistant
versions that expose logging through **Settings → System → Logs**, set this
integration's logging level to **Debug** there and restore it after testing.
You can also use the `logger.set_level` action:

```yaml
action: logger.set_level
data:
  custom_components.autel_http: debug
```

Debug logs record command/realtime/parameter codes, HTTP status, charger error
codes, response durations, request count, charging/connection measurements, and
the chosen next polling interval. They omit PINs, password hashes, tokens,
request headers, charger addresses, and serial numbers; complete request/response
bodies are never logged. Logging adds no charger requests. Restore the level
to `warning` with the same action to end a manually enabled debug session.

## Versions

The integration version is recorded in
[`custom_components/autel_http/manifest.json`](custom_components/autel_http/manifest.json).
Changes are documented in [CHANGELOG.md](CHANGELOG.md). Release tags should match
the manifest version with a `v` prefix, such as `v0.1.3` for version `0.1.3`.
HACS uses published **GitHub releases** for version selection and updates; a Git
tag alone does not create a release. Until releases are published, select `main`
when downloading this custom repository.

## Development

Use Python **3.14.2+** and `uv`:

```bash
uv python install 3.14
uv venv --python 3.14
uv pip sync --require-hashes requirements-dev.lock
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest -q
python3 scripts/package.py
```

Tests load the actual Home Assistant config flow and entity platforms against a
mock HTTPS charger. They cover login/token rejection, exact control addressing,
no retry on ambiguous mutations, units/scaling, connected/stopped states,
options, polling cadence, availability, and unloading. The development lockfile
and CI pin the same Home Assistant/test tool versions. Runtime dependencies are
provided by Home Assistant; no separate Python package installation is needed
for the integration. `scripts/package.py` builds `dist/autel_http.zip` containing
only the component, suitable for extraction into the Home Assistant config folder.
