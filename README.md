# Autel MaxiCharger over HTTPS for Home Assistant

<img src="https://raw.githubusercontent.com/danwoodsy/autel-maxicharger-ha/main/custom_components/autel_http/brand/icon.png" alt="Autel MaxiCharger over HTTPS icon" width="128" height="128">

`autel-maxicharger-ha` provides local HTTPS control and sensors for Home Assistant.

Control an Autel MaxiCharger through its local `https://<charger>/localcfg`
interface. Start/stop and current-limit commands were verified on a single AC
charger, model **EW07-C050000A002**, firmware **V1.05.38**. Home Assistant
**2026.10 or newer** is required; the automated tests run against 2026.10.0.
Other firmware/models need validation against the same interface.

## Install through HACS

[![Open your Home Assistant instance and add this repository to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=danwoodsy&repository=autel-maxicharger-ha&category=integration)

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
| Configuration | **Current limit**, a numeric input from 6–32 A in 1 A steps; **Autostart** on/off switch |
| Sensors | **Status**, **Charging**, **Vehicle connected**, **Charging power** (kW), **Charging current** (A), **Supply voltage** (V), **Session energy** (kWh), **Session duration**, **Meter energy** (kWh) |
| Diagnostic | **Autostart** (read-only), **CPU usage**, **Flash usage**, **HTTP requests per minute**, **Memory usage**, **Network signal quality**, **Refresh**, download diagnostics |
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
connection. Home Assistant sorts the diagnostic entities alphabetically;
with the default names, **Refresh** appears last.

**Network signal quality** displays the Wi-Fi level using these simplified
labels: **4 = very good, 3 = good, 2 = average, 1 = poor, 0 = very poor**.
Its `signal_level` attribute contains the original numeric level. Both use the
same cached network response, with no additional requests. Quality is unknown
for an unrecognized level or when the active network is not Wi-Fi. The level
does not identify the Wi-Fi band or give an exact dBm value.

Upgrading removes the separate **Network signal level** entity. If an automation
used that entity, read the combined sensor's `signal_level` attribute instead.
The existing Wi-Fi quality entity keeps its entity ID and any user customization.
Its internal enum states remain `very_poor`, `weak`, `fair`, `good`, `very_good`
for existing automations; the displayed labels use the wording above.

The integration bundles its own charger/HTTPS icon in `brand/icon.png`, used
by Home Assistant's local brand-image support and included in the manual ZIP.

Pressing **Start charging** or **Stop charging** sends the verified command.
The service returns after its acknowledgement; slow status readback then runs
asynchronously. **Charging** reports actual charger state, so a car that is full
or declines charging can remain off after a successful start command.
**Vehicle connected** remains on when a plugged-in car is stopped.
The existing Status sensor is retained. Charging controls follow these rules:

| Vehicle state | Start | Stop |
| --- | --- | --- |
| Unplugged | Disabled | Disabled |
| Plugged in, not charging | Enabled | Enabled |
| Charging | Disabled | Enabled |
| Connection unknown or charger unreachable | Unavailable | Unavailable |

An unknown charging state also keeps Start unavailable until a successful read
establishes whether the vehicle is charging.

**Autostart** in Configuration changes the charger's persistent permission to
start automatically when a vehicle connects. It uses parameter 4:
`CustomizedPnC: 0` disables it and `2` enables it. Manual HTTPS Start/Stop was
verified with Autostart off. This setting is separate from the current charging
session; use Start/Stop for session control. After a change, the integration
reads Autostart back and displays the reported value. Enabling Autostart can
affect the charger's RFID authorization policy; check the Autel app if you use
RFID cards. The existing read-only Autostart diagnostic entity is preserved.

Unknown state codes are shown as unknown. Sensor failures mark readings
unavailable instead of fabricating zero power or a disconnected vehicle.
The charger can retain session energy after stopping and reset elapsed time;
these entities report its values. Energy counter resets across sessions and
reboots still need characterization, so the energy sensors do not yet enable
long-term energy statistics/Energy dashboard use. Power/current/voltage support
measurement statistics. Temperature is omitted because its raw scale is unverified.

## Refresh settings

Open the integration's **Configure** options:

Choose **High**, **Medium**, **Low**, or **Custom**, and set the timeout for each
HTTPS request. **Medium** is the recommended starting point. Press **Next** to
save a High, Medium, or Low preset and the timeout.

To configure **Custom**:

1. Select **Custom** and press **Next**. Changing the dropdown alone does not
   open the interval fields.
2. Edit the six numeric intervals on the **Custom polling intervals** page;
   each field includes an explanation and seconds beside it.
3. Press **Submit** to save. Until then, the existing settings remain active.

Saving reloads the integration without changing charger settings.

After an update, restart Home Assistant fully and refresh your browser to load
the latest field labels and explanations. Home Assistant caches translations
while it is running.

Preset intervals are in seconds:

| Preset | Unplugged: connection / telemetry / details | Plugged, not charging: status / details | Charging: status / details |
| --- | --- | --- | --- |
| High | 10 / 60 / 150 | 10 / 60 | 5 / 60 |
| **Medium** | **20 / 120 / 300** | **20 / 120** | **10 / 120** |
| Low | 30 / 240 / 600 | 40 / 240 | 20 / 240 |

High halves Medium's intervals. Low doubles them, except that unplugged
connection checks stay at 30 seconds for reasonably quick plug-in detection.
Existing saved numeric intervals are preserved as **Custom** on upgrade;
select **Medium** to adopt the complete recommended schedule.

The request table compares version 0.1.4 with the revised **Medium** schedule:

| Request | Previous schedule (0.1.4) | Unplugged | Plugged, not charging | Charging |
| --- | --- | --- | --- | --- |
| `get_realtime_data`, **2560**, node 60: connection/pilot | 60 s idle / 10 s charging | **20 s** | **20 s** | **10 s** |
| `get_realtime_data`, **1537**, node 10: status, power, current, voltage, session | 60 s idle / 10 s charging | **120 s**, plus immediately on a connection change | **20 s** | **10 s** |
| `get_param_value`, **5**: current limit | 120 s | **300 s** | **120 s** | **120 s** |
| `get_realtime_data`, **2561**, node 60: detailed meter/phase/pilot readings | 120 s | **300 s** | **120 s** | **120 s** |
| `get_param_value`, **4**: Autostart | 120 s | **300 s** | **120 s** | **120 s** |
| `get_current_network`: network signal | 120 s | **300 s** | **120 s** | **120 s** |
| `get_realtime_data`, **1536**, node 10: CPU/memory/flash | 120 s | **300 s** | **120 s** | **120 s** |

Unplugged checks normally send only **one request**, group `2560`. On a detected
connection change, group `1537` is also read in that refresh. This updates vehicle
presence, button availability, and charging telemetry together. Between the
slower unplugged telemetry reads, Home Assistant retains the last readings.
Plugged-in refreshes send **two requests**, `2560` then `1537`. Reporting charging
(`if_work_st: 2`) selects the charging interval; otherwise the plugged-in interval
applies. Autostart runs on the charger independently of Home Assistant polling.

Detailed refreshes add the **five** settings/measurement requests in the table.
The periodic Autostart read keeps changes made in the Autel app visible and
costs one request every 300 seconds unplugged or 120 seconds plugged in on Medium.
Current-limit and Autostart changes made in Home Assistant request immediate
readback of that setting and charging status, without forcing other diagnostics.
Start/Stop also requests immediate status readback. **Refresh** forces all seven
reads and can be used before waiting for the next plug-in check.

Nominal Medium averages are about **4.5 requests/minute unplugged**, **8.5 plugged
in but not charging**, and **14.5 charging**. These exclude login, controls, and
connection transitions; response times lengthen the intervals and lower the
scheduled rate. CPU/memory/network diagnostics can update less often unplugged.
Login and identity discovery run at setup; login also runs when authentication
is rejected. Wi-Fi scans and unrelated settings are not polled.

Custom allows connection/status intervals from 5–3,600 seconds, and unplugged
telemetry/details or plugged-in details up to 86,400 seconds. Charging must be
at least as fast as plugged-in status; additional readings must be at least as
slow as the relevant status interval. Request timeout defaults to **15 seconds**
and accepts **5–60 seconds**.

Requests run **one at a time**. A new normal interval starts after the previous
refresh finishes, so slow replies lengthen the effective interval and never
create overlapping polls. For example, a 5-second setting with two 2–3-second
responses gives about 9–11 seconds between normal refresh starts; a detailed
refresh takes longer. Detailed intervals are checked during normal polls;
they are approximate and can be longer than the selected interval. A pending
control gets a turn after the current HTTP request finishes. **Refresh** requests
a full refresh; repeated presses within one second are combined. Option changes
reload the integration. A failed core poll backs off to at least **60 seconds**;
Refresh remains available for recovery.

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

Maintainers: [HACS publishing and release instructions](docs/hacs-publishing.md)
cover validation, the first release, default catalog submission, and future
version updates.

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
