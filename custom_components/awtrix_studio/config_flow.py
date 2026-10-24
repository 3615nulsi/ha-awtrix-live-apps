"""Config flow: one entry per clock, one subentry per app."""

from __future__ import annotations

import re
from typing import Any

try:  # Home Assistant 2026.x replaced voluptuous with its fork, probatio.
    import probatio as vol
except ImportError:  # pragma: no cover - older Home Assistant
    import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TemplateSelector,
    TextSelector,
)
from homeassistant.helpers.template import Template

from .const import (
    APP_NAME_PATTERN,
    CONF_APP_NAME,
    CONF_CYCLE_ONLY_ON_SCREEN,
    CONF_FIRMWARE,
    CONF_HIDE_WHEN_EMPTY,
    CONF_LIFETIME,
    CONF_PAGE_INTERVAL,
    CONF_PREFIX,
    CONF_TEMPLATE,
    DEFAULT_CYCLE_ONLY_ON_SCREEN,
    DEFAULT_HIDE_WHEN_EMPTY,
    DEFAULT_LIFETIME,
    DEFAULT_PAGE_INTERVAL,
    DEFAULT_PREFIX,
    DOMAIN,
    FIRMWARE_AWTRIX3,
    MAX_LIFETIME,
    MAX_PAGE_INTERVAL,
    MIN_PAGE_INTERVAL,
    SUBENTRY_TYPE_APP,
)
from .drivers import DRIVERS
from .pages import InvalidPagesError, parse_pages

MQTT_DOMAIN = "mqtt"


def _normalize_prefix(prefix: str) -> str | None:
    """Return a clean MQTT prefix, or None if it is not usable."""
    prefix = prefix.strip().strip("/")
    if not prefix or any(char in prefix for char in "#+ "):
        return None
    return prefix


class AwtrixStudioConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a clock."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the firmware and the MQTT prefix."""
        if not self.hass.config_entries.async_entries(MQTT_DOMAIN):
            return self.async_abort(reason="mqtt_not_configured")

        errors: dict[str, str] = {}
        if user_input is not None:
            prefix = _normalize_prefix(user_input[CONF_PREFIX])
            if prefix is None:
                errors[CONF_PREFIX] = "invalid_prefix"
            else:
                await self.async_set_unique_id(prefix)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=prefix,
                    data={
                        CONF_FIRMWARE: user_input[CONF_FIRMWARE],
                        CONF_PREFIX: prefix,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_FIRMWARE, default=FIRMWARE_AWTRIX3): SelectSelector(
                    SelectSelectorConfig(
                        options=list(DRIVERS),
                        translation_key=CONF_FIRMWARE,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_PREFIX, default=DEFAULT_PREFIX): TextSelector(),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Apps are subentries of a clock."""
        return {SUBENTRY_TYPE_APP: AppSubentryFlow}


class AppSubentryFlow(ConfigSubentryFlow):
    """Add or edit an app."""

    @property
    def _is_new(self) -> bool:
        return self.source == "user"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add an app."""
        return await self.async_step_app(user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Edit an app."""
        return await self.async_step_app(user_input)

    async def async_step_app(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Show and validate the app form."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {"error": ""}

        if user_input is not None:
            data = dict(user_input)
            if self._is_new:
                name = data[CONF_APP_NAME].strip()
                data[CONF_APP_NAME] = name
                if not re.fullmatch(APP_NAME_PATTERN, name):
                    errors[CONF_APP_NAME] = "invalid_app_name"
                elif name in self._existing_app_names():
                    errors[CONF_APP_NAME] = "app_name_exists"
            else:
                data[CONF_APP_NAME] = self._get_reconfigure_subentry().data[
                    CONF_APP_NAME
                ]

            if error := self._validate_template(data[CONF_TEMPLATE]):
                errors[CONF_TEMPLATE] = error[0]
                placeholders["error"] = error[1]

            data[CONF_LIFETIME] = int(data.get(CONF_LIFETIME, DEFAULT_LIFETIME))

            if not errors:
                if self._is_new:
                    return self.async_create_entry(
                        title=data[CONF_APP_NAME],
                        data=data,
                        unique_id=data[CONF_APP_NAME],
                    )
                return self.async_update_and_abort(
                    self._get_entry(),
                    self._get_reconfigure_subentry(),
                    data=data,
                )
            suggested: dict[str, Any] | None = user_input
        elif self._is_new:
            suggested = None
        else:
            suggested = dict(self._get_reconfigure_subentry().data)

        return self.async_show_form(
            step_id="app",
            data_schema=self.add_suggested_values_to_schema(self._schema(), suggested),
            errors=errors,
            description_placeholders=placeholders,
        )

    def _schema(self) -> vol.Schema:
        fields: dict[Any, Any] = {}
        if self._is_new:
            fields[vol.Required(CONF_APP_NAME)] = TextSelector()
        fields.update(
            {
                vol.Required(CONF_TEMPLATE): TemplateSelector(),
                vol.Required(
                    CONF_PAGE_INTERVAL, default=DEFAULT_PAGE_INTERVAL
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_PAGE_INTERVAL,
                        max=MAX_PAGE_INTERVAL,
                        step=0.1,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_CYCLE_ONLY_ON_SCREEN, default=DEFAULT_CYCLE_ONLY_ON_SCREEN
                ): BooleanSelector(),
                vol.Required(
                    CONF_HIDE_WHEN_EMPTY, default=DEFAULT_HIDE_WHEN_EMPTY
                ): BooleanSelector(),
                vol.Required(CONF_LIFETIME, default=DEFAULT_LIFETIME): NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        max=MAX_LIFETIME,
                        step=1,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return vol.Schema(fields)

    def _existing_app_names(self) -> set[str]:
        return {
            subentry.data.get(CONF_APP_NAME)
            for subentry in self._get_entry().subentries.values()
            if subentry.subentry_type == SUBENTRY_TYPE_APP
        }

    def _validate_template(self, template_str: str) -> tuple[str, str] | None:
        """Render the template once; return (error key, detail) if it fails."""
        template = Template(template_str, self.hass)
        try:
            template.ensure_valid()
            result = template.async_render(parse_result=True)
        except TemplateError as err:
            return "invalid_template", str(err)
        try:
            parse_pages(result)
        except InvalidPagesError as err:
            return "invalid_pages", str(err)
        return None
