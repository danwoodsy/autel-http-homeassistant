# Autel MaxiCharger over HTTPS for Home Assistant

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
| Diagnostic | **Autostart** (read-only), **Refresh**, download diagnostics |
| Diagnostic, initially disabled | Phase A/B/C current, pilot voltage/duty cycle, network signal level |

The current limit is further capped by the discovered connector rating and
its reported offline-current ceiling. The device name, entity names, and area
can be changed using Home Assistant's usual controls. Enable additional
diagnostic entities on the device's entity page; this adds no polling requests.

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

| Option | Default | Allowed |
| --- | --- | --- |
| Status refresh interval | 30 seconds | 15–3,600 seconds |
| Detailed refresh interval | 120 seconds | Status interval–86,400 seconds |
| Timeout per HTTPS request | 15 seconds | 5–60 seconds |

Each normal refresh sends **three** requests: connector telemetry (`1537`),
controller/connection status (`2560`), and configured current (`parameter 5`).
When detailed polling is due, **three** more fetch detailed meter/pilot/phase
measurements (`2561`), Autostart (`parameter 4`), and network status.
Login and identity discovery run at setup; login also runs when authentication
is rejected. Wi-Fi scans and unrelated settings are not polled.

Requests run **one at a time**. A new normal interval starts after the previous
refresh finishes, so slow replies lengthen the effective interval and never
create overlapping polls. Detailed intervals are checked during normal polls;
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
