"""Small shared helpers for platform setup and value scaling."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .entity import TuyaLanEntity


def async_setup_profile_platform(
    hass: HomeAssistant,
    entry: ConfigEntry,
    platform: str,
    factory: Callable[[Any, dict[str, Any], str], TuyaLanEntity],
    async_add_entities: Callable[[Iterable[TuyaLanEntity]], None],
) -> None:
    """Instantiate every profile entity that targets ``platform``."""
    runtime = hass.data[DOMAIN]["entries"][entry.entry_id]
    profile = runtime.profile
    if profile is None:
        return
    entities = [
        factory(runtime.coordinator, desc, entry.title)
        for desc in profile.entities
        if desc.get("platform") == platform
    ]
    if entities:
        async_add_entities(entities)


def scale_from_device(value: Any, options: dict[str, Any]) -> Any:
    """Apply ``scale`` / ``offset`` when reading a raw DP value."""
    if not isinstance(value, (int, float)):
        return value
    scale = options.get("scale", 1) or 1
    offset = options.get("offset", 0) or 0
    return (value / scale) + offset


def scale_to_device(value: float, options: dict[str, Any]) -> int | float:
    scale = options.get("scale", 1) or 1
    offset = options.get("offset", 0) or 0
    raw = (value - offset) * scale
    return round(raw) if options.get("integer", True) else raw
