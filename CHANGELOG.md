# Changelog

Version numbers below identify integration revisions. GitHub releases will use
matching `v` tags, for example `v0.1.3` for manifest version `0.1.3`.

## 0.1.6 — 2026-10-11

- Merge signal diagnostics into Network signal quality with the raw 0–4 level
  as an attribute. Remove the duplicate numeric entity on upgrade and retain
  the quality entity's ID and user customization.
- Display signal quality as very good, good, average, poor, or very poor.
  The combined sensor's name places Refresh last in the default diagnostic list.
- Show Next on the polling preset page and explain how Custom opens the six
  interval fields, followed by Submit to save.
- Add HACS/Hassfest validation, a gated versioned-release workflow, first-release
  notes, and instructions for submitting the integration to HACS's catalog.

## 0.1.5 — 2026-10-11

- Add an Autostart configuration switch using HTTPS parameter 4, with 0 for off
  and 2 for on. Read the setting back after each accepted change and preserve
  the existing read-only diagnostic entity.
- Share the existing permission reading and request a targeted readback after
  an accepted switch change without displaying an optimistic state.
- Disable both charging buttons while unplugged or connection is unknown;
  disable Start while charging and keep Stop enabled while connected.
- Add High/Medium/Low polling presets and Custom intervals. Check connection
  more often unplugged while reading telemetry and diagnostics less often.
  Preserve existing numeric options as Custom and document the request schedules.

## 0.1.4 — 2026-10-11

- Add Wi-Fi signal quality using the charger's frontend labels, from Very poor
  to Very good. Preserve the numeric signal-level entity and use the same
  cached network response, without additional charger requests.

## 0.1.3 — 2026-10-11

- Explain each polling setting directly beneath its input, including the
  readings refreshed, suggested intervals, request counts, and timing limits.
- Use numeric inputs with seconds shown beside all four settings.
- Clarify that refresh intervals start after the previous refresh completes,
  and that request timeout controls the wait for an individual response.

## 0.1.2

- Add separate charging and idle refresh intervals, defaulting to 10 and
  60 seconds. Preserve existing saved status intervals for idle polling.
- Reduce routine status refreshes to two requests. Read current-limit settings
  on the detailed interval and immediately after a Home Assistant limit change.
- Add a local HTTP requests-per-minute sensor and request timing diagnostics.
- Add debug logs for requests, errors, charging measurements, and polling
  decisions while excluding credentials and charger identifiers.
- Update the integration icon with green lights and an HTTP badge.

## 0.1.1

- Add CPU, memory, flash usage, and network signal diagnostics.
- Replace the request-timeout slider with a numeric input.
- Bundle a local integration icon and include it in the manual-install ZIP.

## 0.1.0

- Add local HTTPS setup using the charger's address, username, and PIN.
- Add verified start/stop controls, a 6–32 A current-limit input, and charging
  and connection sensors.
- Add configurable polling, authentication renewal on rejection, cached
  diagnostics, and serialized requests to the charger.
