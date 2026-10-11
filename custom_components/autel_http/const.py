"""Constants for the Autel MaxiCharger over HTTPS integration."""

from homeassistant.const import Platform

DOMAIN = "autel_http"
PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SENSOR,
]
CONF_PIN = "pin"
CONF_STATUS_INTERVAL = "status_interval"
CONF_CHARGING_INTERVAL = "charging_interval"
CONF_DETAILS_INTERVAL = "details_interval"
CONF_REQUEST_TIMEOUT = "request_timeout"
DEFAULT_STATUS_INTERVAL = 60
DEFAULT_CHARGING_INTERVAL = 10
DEFAULT_DETAILS_INTERVAL = 120
DEFAULT_REQUEST_TIMEOUT = 15
MIN_STATUS_INTERVAL = 15
MIN_CHARGING_INTERVAL = 5
MIN_CURRENT = 6
MAX_CURRENT = 32

# The charger's frontend labels its Wi-Fi signal levels with these terms.
WIFI_SIGNAL_QUALITY = {
    0: "very_poor",
    1: "weak",
    2: "fair",
    3: "good",
    4: "very_good",
}

CHARGER_STATES = {
    0: "idle",
    1: "preparing",
    2: "charging",
    3: "suspended_by_charger",
    4: "suspended_by_vehicle",
    5: "completed",
    6: "reserved",
    7: "unavailable",
    8: "fault",
}
