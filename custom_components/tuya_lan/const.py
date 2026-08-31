"""Constants for the Tuya-LAN integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "tuya_lan"

# --- Config entry / discovery keys -------------------------------------------------
CONF_DEVICE_ID: Final = "device_id"
CONF_LOCAL_KEY: Final = "local_key"
CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_PROTOCOL_VERSION: Final = "protocol_version"
CONF_PROFILE: Final = "profile"
CONF_PRODUCT_KEY: Final = "product_key"
CONF_GATEWAY_ID: Final = "gateway_id"  # parent device id for sub-devices
CONF_NODE_ID: Final = "node_id"  # cid / sub-device id on a gateway
CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_MANUAL: Final = "manual"
CONF_DPS_OVERRIDES: Final = "dps_overrides"
CONF_ENTITIES: Final = "entities"

# Special profile sentinels chosen in the config flow.
PROFILE_DETECT: Final = "__detect__"
PROFILE_RAW: Final = "__raw__"

DEFAULT_PORT: Final = 6668
DEFAULT_POLL_INTERVAL: Final = 30  # seconds; local_push devices still get a heartbeat poll
RECONNECT_INTERVAL: Final = 15  # seconds between reconnect attempts

# Supported protocol versions, newest first (used for auto-probing).
SUPPORTED_VERSIONS: Final = ("3.5", "3.4", "3.3", "3.2", "3.1")
DEFAULT_VERSION: Final = "3.3"

# --- Discovery -------------------------------------------------------------------
UDP_PORT_PLAIN: Final = 6666  # protocol 3.1 broadcasts (plaintext)
UDP_PORT_ENCRYPTED: Final = 6667  # protocol 3.2-3.4 broadcasts (AES-ECB, well-known key)
UDP_PORT_V35: Final = 6699  # protocol 3.5 broadcasts (AES-GCM, well-known key)
# md5("yGAdlopoPVldABfn")[4:20] -- the well-known UDP broadcast key, published for years.
UDP_KEY_SEED: Final = b"yGAdlopoPVldABfn"

DISCOVERY_SIGNAL: Final = f"{DOMAIN}_discovery"
DISCOVERY_CACHE: Final = f"{DOMAIN}_discovery_cache"

# --- Events / services ----------------------------------------------------------
EVENT_DP_UPDATE: Final = f"{DOMAIN}_dp"
SERVICE_SET_DP: Final = "set_dp"
SERVICE_DUMP_DPS: Final = "dump_dps"
SERVICE_RELOAD_PROFILES: Final = "reload_profiles"

# --- Platforms exposed by profiles --------------------------------------------------
PLATFORMS: Final = (
    "binary_sensor",
    "button",
    "climate",
    "cover",
    "fan",
    "humidifier",
    "light",
    "number",
    "select",
    "sensor",
    "switch",
)
