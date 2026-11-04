import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.helpers import selector

DOMAIN = "System_1-2_Dual_AI"

DEFAULT_SYS1 = "You are a smart home router. The user is in the '{room}'. If the command controls a device, match it to the exact entity_id below and return JSON with 'domain', 'service', and 'entity_id'. If it is a general question, return: {\"domain\": \"chat\", \"service\": \"chat\", \"entity_id\": \"none\"}\n\nAVAILABLE ENTITIES:\n{entities}\n\nOutput ONLY raw JSON. No markdown formatting."
DEFAULT_SYS2 = "You are a helpful smart home AI. The current time is {time}. If the user asked a question, answer it concisely. If the user issued a device command, summarize the Action State into a natural, single-sentence spoken reply."

class EcholocalAIFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return EcholocalAIOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            self.providers = user_input
            return await self.async_step_models()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("sys1_provider", default="Ollama"): vol.In(["Ollama", "OpenRouter"]),
                vol.Required("sys2_provider", default="OpenRouter"): vol.In(["Ollama", "OpenRouter"]),
            })
        )

    async def async_step_models(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="Echolocal Dual Engine", data={**self.providers, **user_input})

        schema = {
            vol.Required("sys1_model", default="tev1-4b-decision"): str,
            vol.Optional("sys1_prompt", default=DEFAULT_SYS1): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
            vol.Required("sys2_model", default="anthropic/claude-3.5-sonnet"): str,
            vol.Optional("sys2_prompt", default=DEFAULT_SYS2): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
        }
        
        has_or = "OpenRouter" in [self.providers["sys1_provider"], self.providers["sys2_provider"]]
        has_ol = "Ollama" in [self.providers["sys1_provider"], self.providers["sys2_provider"]]

        if has_or: schema[vol.Required(CONF_API_KEY, default="")] = str
        if has_ol: schema[vol.Required(CONF_URL, default="http://192.168.86.41:11434/api/generate")] = str

        return self.async_show_form(step_id="models", data_schema=vol.Schema(schema))


class EcholocalAIOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            self.providers = user_input
            return await self.async_step_models()

        opts = self.config_entry.options
        data = self.config_entry.data
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("sys1_provider", default=opts.get("sys1_provider", data.get("sys1_provider", "Ollama"))): vol.In(["Ollama", "OpenRouter"]),
                vol.Required("sys2_provider", default=opts.get("sys2_provider", data.get("sys2_provider", "OpenRouter"))): vol.In(["Ollama", "OpenRouter"]),
            })
        )

    async def async_step_models(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data={**self.providers, **user_input})

        opts = self.config_entry.options
        data = self.config_entry.data
        
        schema = {
            vol.Required("sys1_model", default=opts.get("sys1_model", data.get("sys1_model"))): str,
            vol.Optional("sys1_prompt", default=opts.get("sys1_prompt", data.get("sys1_prompt", DEFAULT_SYS1))): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
            vol.Required("sys2_model", default=opts.get("sys2_model", data.get("sys2_model"))): str,
            vol.Optional("sys2_prompt", default=opts.get("sys2_prompt", data.get("sys2_prompt", DEFAULT_SYS2))): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
        }
        
        has_or = "OpenRouter" in [self.providers["sys1_provider"], self.providers["sys2_provider"]]
        has_ol = "Ollama" in [self.providers["sys1_provider"], self.providers["sys2_provider"]]

        if has_or: schema[vol.Required(CONF_API_KEY, default=opts.get(CONF_API_KEY, data.get(CONF_API_KEY, "")))] = str
        if has_ol: schema[vol.Required(CONF_URL, default=opts.get(CONF_URL, data.get(CONF_URL, "http://192.168.86.41:11434/api/generate")))] = str

        return self.async_show_form(step_id="models", data_schema=vol.Schema(schema))