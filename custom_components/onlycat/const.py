"""Constants for OnlyCat."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "onlycat"
ATTRIBUTION = ""
CONF_IGNORE_FLAP_MOTION_RULES = "ignore_flap_motion_rules"
CONF_IGNORE_MOTION_SENSOR_RULES = "ignore_motion_sensor_rules"
CONF_POLL_INTERVAL_HOURS = "poll_interval_hours"
CONF_ENABLE_DETAILED_METRICS = "enable_detailed_metrics"
