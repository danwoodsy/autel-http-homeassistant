# Changelog

Version numbers below identify integration revisions. GitHub releases will use
matching `v` tags, for example `v0.1.3` for manifest version `0.1.3`.

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
