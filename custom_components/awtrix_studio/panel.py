"""The sidebar panel: static files and registration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PANEL_URL_PATH = "awtrix-studio"
STATIC_URL = f"/{DOMAIN}_static"
WEBCOMPONENT = "awtrix-studio-panel"
FRONTEND_DIR = Path(__file__).parent / "frontend"


async def async_register_panel(hass: HomeAssistant) -> None:
    """Serve the panel's script and add it to the sidebar (admins only)."""
    if "frontend" not in hass.config.components or getattr(hass, "http", None) is None:
        _LOGGER.debug("Frontend not loaded, the panel is not registered")
        return

    # Imported here so that the integration also works without the frontend.
    from homeassistant.components import panel_custom  # noqa: PLC0415
    from homeassistant.components.frontend import async_panel_exists  # noqa: PLC0415
    from homeassistant.components.http import StaticPathConfig  # noqa: PLC0415

    if async_panel_exists(hass, PANEL_URL_PATH):
        return

    integration = await async_get_integration(hass, DOMAIN)
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(FRONTEND_DIR), cache_headers=False)]
    )
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=WEBCOMPONENT,
        sidebar_title="Awtrix Studio",
        sidebar_icon="mdi:dots-grid",
        module_url=f"{STATIC_URL}/{WEBCOMPONENT}.js?v={integration.version}",
        require_admin=True,
        config={},
    )
