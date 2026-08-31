"""Device profiles: YAML descriptions that map data points (DPs) to HA entities.

A profile is a plain dict with this shape::

    id: generic_switch
    name: Generic switch / plug
    match:                       # optional - used to auto-suggest a profile
      product_key: [key1, key2]
      required_dps: [1]
      any_dps: [1, 7, 9]
    entities:
      - platform: switch
        name: null               # null -> use the device name
        dps:
          switch: "1"
        icon: mdi:power-socket
        # ...platform-specific keys...

Bundled profiles live next to this file. User profiles live in
``<config>/tuya_lan/profiles/*.yaml`` and win on an id clash.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import voluptuous as vol
import yaml

_LOGGER = logging.getLogger(__name__)

_BUNDLED_DIR = Path(__file__).parent

ENTITY_SCHEMA = vol.Schema(
    {
        vol.Required("platform"): str,
        vol.Optional("name"): vol.Any(None, str),
        vol.Optional("key"): str,  # stable suffix for the entity unique_id
        vol.Required("dps"): {str: vol.Any(str, int)},
        vol.Optional("device_class"): vol.Any(None, str),
        vol.Optional("state_class"): vol.Any(None, str),
        vol.Optional("unit_of_measurement"): vol.Any(None, str),
        vol.Optional("entity_category"): vol.Any(None, "config", "diagnostic"),
        vol.Optional("icon"): vol.Any(None, str),
        vol.Optional("options"): dict,  # e.g. select options, light ranges, scaling
    },
    extra=vol.ALLOW_EXTRA,
)

MATCH_SCHEMA = vol.Schema(
    {
        vol.Optional("product_key"): vol.Any(str, [str]),
        vol.Optional("required_dps"): [vol.Coerce(str)],
        vol.Optional("any_dps"): [vol.Coerce(str)],
        vol.Optional("version"): vol.Any(str, [str]),
    }
)

PROFILE_SCHEMA = vol.Schema(
    {
        vol.Required("id"): str,
        vol.Required("name"): str,
        vol.Optional("match", default=dict): MATCH_SCHEMA,
        vol.Required("entities"): [ENTITY_SCHEMA],
    }
)


@dataclass(slots=True)
class Profile:
    id: str
    name: str
    entities: list[dict[str, Any]]
    match: dict[str, Any] = field(default_factory=dict)
    source: str = "bundled"

    def score(self, *, product_key: str | None, dps: set[str], version: str | None) -> int:
        """How well this profile fits an observed device. Higher is better; <=0 = no."""
        m = self.match
        if not m:
            return 0
        score = 0
        pk = m.get("product_key")
        if pk:
            keys = [pk] if isinstance(pk, str) else list(pk)
            if product_key and product_key in keys:
                score += 100
            elif product_key:
                return -1  # explicit product key given and it does not match
        req = {str(x) for x in m.get("required_dps", [])}
        if req:
            if not req.issubset(dps):
                return -1
            score += 10 * len(req)
        any_dps = {str(x) for x in m.get("any_dps", [])}
        if any_dps:
            overlap = len(any_dps & dps)
            if not overlap:
                return -1
            score += overlap
        ver = m.get("version")
        if ver:
            allowed = [ver] if isinstance(ver, str) else list(ver)
            if version and version not in allowed:
                return -1
        return score


def _load_file(path: Path, source: str) -> Profile | None:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        data = PROFILE_SCHEMA(raw)
    except (OSError, yaml.YAMLError, vol.Invalid) as err:
        _LOGGER.warning("skipping invalid profile %s: %s", path.name, err)
        return None
    return Profile(
        id=data["id"],
        name=data["name"],
        entities=data["entities"],
        match=data.get("match") or {},
        source=source,
    )


def load_profiles(user_dir: Path | None = None) -> dict[str, Profile]:
    """Load bundled profiles, then overlay user profiles (user id wins)."""
    profiles: dict[str, Profile] = {}
    for path in sorted(_BUNDLED_DIR.glob("*.yaml")):
        prof = _load_file(path, "bundled")
        if prof:
            profiles[prof.id] = prof
    if user_dir and user_dir.is_dir():
        for path in sorted(user_dir.glob("*.yaml")):
            prof = _load_file(path, "user")
            if prof:
                profiles[prof.id] = prof
    return profiles


def suggest_profile(
    profiles: dict[str, Profile],
    *,
    product_key: str | None,
    dps: set[str],
    version: str | None,
) -> Profile | None:
    best: tuple[int, Profile] | None = None
    for prof in profiles.values():
        s = prof.score(product_key=product_key, dps=dps, version=version)
        if s > 0 and (best is None or s > best[0]):
            best = (s, prof)
    return best[1] if best else None
