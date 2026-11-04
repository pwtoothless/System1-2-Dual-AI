import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY, CONF_URL

DOMAIN = "System_1-2_Dual_AI"

class EcholocalAIFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="System 1 & 2 Dual AI", data=user_input)

        schema = vol.Schema({
            vol.Required("sys1_provider", default="Ollama"): vol.In(["Ollama", "OpenRouter"]),
            vol.Required("sys1_model", default="tev1-4b-decision"): str,
            vol.Required("sys2_provider", default="OpenRouter"): vol.In(["Ollama", "OpenRouter"]),
            vol.Required("sys2_model", default="meta-llama/llama-3.1-8b-instruct"): str,
            vol.Optional(CONF_URL, default="http://192.168.86.41:11434/api/generate"): str,
            vol.Optional(CONF_API_KEY, default=""): str,
        })
        
        return self.async_show_form(step_id="user", data_schema=schema)