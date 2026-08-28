"""Constants for the TimeTree integration."""

DOMAIN = "timetree"
CONF_CALENDAR_ID = "calendar_id"
CONF_CALENDAR_NAME = "calendar_name"
CONF_CALENDAR_USERS = "calendar_users"
CONF_CALENDAR_LABELS = "calendar_labels"
CONF_SYNC_MODE = "sync_mode"
CONF_SCAN_INTERVAL = "scan_interval"

SYNC_MODE_COMBINED = "combined"
SYNC_MODE_INDIVIDUAL = "individual"
UNASSIGNED_MEMBER_ID = "unassigned"

DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 120

LOGGER_NAME = "custom_components.timetree"