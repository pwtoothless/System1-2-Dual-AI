"""Config flow for System 1 & 2 Dual AI integration."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.core import callback
from homeassistant.helpers import selector

DOMAIN = "system_1_2_dual_ai"

DEFAULT_OLLAMA_URL = "http://192.168.86.41:11434/api/generate"
DEFAULT_EXPOSED_ONLY = True
DEFAULT_GRANULARITY = "full"

GRANULARITY_OPTIONS = [
    selector.SelectOptionDict(
        value="full",
        label="Full (On / Off / Toggle) — Recommended for ≤ 80 devices",
    ),
    selector.SelectOptionDict(
        value="compact",
        label="Compact (On / Off) — Recommended for 81–125 devices",
    ),
    selector.SelectOptionDict(
        value="state_aware",
        label="Minimal (State-aware single action) — Recommended for 126–254 devices",
    ),
]
DEFAULT_SYS1 = (
    "You are a smart home router. The user is in the '{room}'. "
    "Pick the most appropriate action from the choices to fulfill the command. "
    "If the user asks a general question, select 'CHAT'."
)
DEFAULT_SYS2 = (
    "You are a helpful smart home AI. The current time is {time}. "
    "If the user asked a question, answer it concisely. "
    "If the user issued a device command, summarize the Action State into a natural, "
    "single-sentence spoken reply."
)


def _validate_models_input(
    providers: dict[str, Any], user_input: dict[str, Any]
) -> dict[str, str]:
    """Validate provider-specific configuration fields."""
    errors: dict[str, str] = {}
    selected = {providers.get("sys1_provider"), providers.get("sys2_provider")}

    if "OpenRouter" in selected and not user_input.get(CONF_API_KEY, "").strip():
        errors[CONF_API_KEY] = "missing_api_key"

    if "Ollama" in selected:
        url = user_input.get(CONF_URL, "").strip()
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            errors[CONF_URL] = "invalid_url"

    return errors


class System12DualAIConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for System 1 & 2 Dual AI."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.providers: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> System12DualAIOptionsFlow:
        """Return the options flow handler."""
        return System12DualAIOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial provider selection step."""
        if user_input is not None:
            self.providers = user_input
            return await self.async_step_models()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("sys1_provider", default="Ollama"): vol.In(
                        ["Ollama", "OpenRouter"]
                    ),
                    vol.Required("sys2_provider", default="OpenRouter"): vol.In(
                        ["Ollama", "OpenRouter"]
                    ),
                }
            ),
        )

    async def async_step_models(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the model and credential configuration step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_models_input(self.providers, user_input)
            if not errors:
                return self.async_create_entry(
                    title="System 1 & 2 Dual AI",
                    data={**self.providers, **user_input},
                )

        schema: dict[Any, Any] = {
            vol.Required("sys1_model", default="tev1-4b-decision"): str,
            vol.Optional("sys1_prompt", default=DEFAULT_SYS1): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
            vol.Required("sys2_model", default="anthropic/claude-3.5-sonnet"): str,
            vol.Optional("sys2_prompt", default=DEFAULT_SYS2): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
            vol.Optional("exposed_only", default=DEFAULT_EXPOSED_ONLY): bool,
            vol.Required(
                "control_granularity", default=DEFAULT_GRANULARITY
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=GRANULARITY_OPTIONS,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }

        selected = {self.providers["sys1_provider"], self.providers["sys2_provider"]}
        if "OpenRouter" in selected:
            schema[vol.Required(CONF_API_KEY, default="")] = selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            )
        if "Ollama" in selected:
            schema[vol.Required(CONF_URL, default=DEFAULT_OLLAMA_URL)] = str

        return self.async_show_form(
            step_id="models",
            data_schema=vol.Schema(schema),
            errors=errors,
        )


class System12DualAIOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for System 1 & 2 Dual AI."""

    def __init__(self) -> None:
        """Initialize the options flow."""
        self.providers: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial provider selection step."""
        if user_input is not None:
            self.providers = user_input
            return await self.async_step_models()

        opts = self.config_entry.options
        data = self.config_entry.data

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "sys1_provider",
                        default=opts.get(
                            "sys1_provider", data.get("sys1_provider", "Ollama")
                        ),
                    ): vol.In(["Ollama", "OpenRouter"]),
                    vol.Required(
                        "sys2_provider",
                        default=opts.get(
                            "sys2_provider", data.get("sys2_provider", "OpenRouter")
                        ),
                    ): vol.In(["Ollama", "OpenRouter"]),
                }
            ),
        )

    async def async_step_models(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the model and credential configuration step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_models_input(self.providers, user_input)
            if not errors:
                return self.async_create_entry(
                    title="",
                    data={**self.providers, **user_input},
                )

        opts = self.config_entry.options
        data = self.config_entry.data

        schema: dict[Any, Any] = {
            vol.Required(
                "sys1_model",
                default=opts.get("sys1_model", data.get("sys1_model", "tev1-4b-decision")),
            ): str,
            vol.Optional(
                "sys1_prompt",
                default=opts.get("sys1_prompt", data.get("sys1_prompt", DEFAULT_SYS1)),
            ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
            vol.Required(
                "sys2_model",
                default=opts.get(
                    "sys2_model", data.get("sys2_model", "anthropic/claude-3.5-sonnet")
                ),
            ): str,
            vol.Optional(
                "sys2_prompt",
                default=opts.get("sys2_prompt", data.get("sys2_prompt", DEFAULT_SYS2)),
            ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
            vol.Optional(
                "exposed_only",
                default=opts.get(
                    "exposed_only", data.get("exposed_only", DEFAULT_EXPOSED_ONLY)
                ),
            ): bool,
            vol.Required(
                "control_granularity",
                default=opts.get(
                    "control_granularity",
                    data.get("control_granularity", DEFAULT_GRANULARITY),
                ),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=GRANULARITY_OPTIONS,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }

        selected = {self.providers["sys1_provider"], self.providers["sys2_provider"]}
        if "OpenRouter" in selected:
            schema[
                vol.Required(
                    CONF_API_KEY,
                    default=opts.get(CONF_API_KEY, data.get(CONF_API_KEY, "")),
                )
            ] = selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            )
        if "Ollama" in selected:
            schema[
                vol.Required(
                    CONF_URL,
                    default=opts.get(CONF_URL, data.get(CONF_URL, DEFAULT_OLLAMA_URL)),
                )
            ] = str

        return self.async_show_form(
            step_id="models",
            data_schema=vol.Schema(schema),
            errors=errors,
        )
