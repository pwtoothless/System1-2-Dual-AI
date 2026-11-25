"""Unit tests for System 1 & 2 Dual AI conversation entity."""

from __future__ import annotations

import importlib
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _install_ha_stubs() -> None:
    """Install lightweight Home Assistant and aiohttp stubs for local unit testing."""
    if "aiohttp" not in sys.modules:
        try:
            import aiohttp  # noqa: F401
        except ImportError:
            aiohttp_pkg = types.ModuleType("aiohttp")
            aiohttp_pkg.ClientSession = object
            aiohttp_pkg.ClientTimeout = lambda **kwargs: None
            sys.modules["aiohttp"] = aiohttp_pkg

    if "homeassistant" in sys.modules:
        return

    ha = types.ModuleType("homeassistant")
    components = types.ModuleType("homeassistant.components")
    conv_mod = types.ModuleType("homeassistant.components.conversation")
    ha_comp = types.ModuleType("homeassistant.components.homeassistant")
    exposed_mod = types.ModuleType(
        "homeassistant.components.homeassistant.exposed_entities"
    )
    config_entries = types.ModuleType("homeassistant.config_entries")
    const_mod = types.ModuleType("homeassistant.const")
    core_mod = types.ModuleType("homeassistant.core")
    helpers_mod = types.ModuleType("homeassistant.helpers")
    ar_mod = types.ModuleType("homeassistant.helpers.area_registry")
    dr_mod = types.ModuleType("homeassistant.helpers.device_registry")
    er_mod = types.ModuleType("homeassistant.helpers.entity_registry")
    intent_mod = types.ModuleType("homeassistant.helpers.intent")
    service_mod = types.ModuleType("homeassistant.helpers.service")
    aiohttp_mod = types.ModuleType("homeassistant.helpers.aiohttp_client")
    ent_plat_mod = types.ModuleType("homeassistant.helpers.entity_platform")

    class ConversationEntity:
        pass

    class ConversationEntityFeature:
        CONTROL = 1

    class ConversationInput:
        def __init__(
            self,
            text: str,
            device_id: str | None = None,
            language: str = "en",
            conversation_id: str = "conv-1",
        ) -> None:
            self.text = text
            self.device_id = device_id
            self.language = language
            self.conversation_id = conversation_id

    class ConversationResult:
        def __init__(self, response, conversation_id: str) -> None:
            self.response = response
            self.conversation_id = conversation_id

    class IntentResponse:
        def __init__(self, language: str = "en") -> None:
            self.language = language
            self.speech: dict = {}

        def async_set_speech(self, text: str) -> None:
            self.speech = {"plain": {"speech": text}}

    conv_mod.DOMAIN = "conversation"
    conv_mod.ConversationEntity = ConversationEntity
    conv_mod.ConversationEntityFeature = ConversationEntityFeature
    conv_mod.ConversationInput = ConversationInput
    conv_mod.ConversationResult = ConversationResult

    exposed_mod.async_should_expose = lambda hass, domain, eid: True
    const_mod.CONF_API_KEY = "api_key"
    const_mod.CONF_URL = "url"
    config_entries.ConfigEntry = object
    core_mod.HomeAssistant = object

    ar_mod.async_get = lambda hass: MagicMock()
    dr_mod.async_get = lambda hass: MagicMock()
    er_mod.async_get = lambda hass: MagicMock()
    intent_mod.IntentResponse = IntentResponse
    service_mod.async_get_all_descriptions = AsyncMock(return_value={})
    aiohttp_mod.async_get_clientsession = lambda hass: MagicMock()
    ent_plat_mod.AddEntitiesCallback = object

    helpers_mod.area_registry = ar_mod
    helpers_mod.device_registry = dr_mod
    helpers_mod.entity_registry = er_mod
    helpers_mod.intent = intent_mod
    helpers_mod.service = service_mod

    sys.modules["homeassistant"] = ha
    sys.modules["homeassistant.components"] = components
    sys.modules["homeassistant.components.conversation"] = conv_mod
    sys.modules["homeassistant.components.homeassistant"] = ha_comp
    sys.modules["homeassistant.components.homeassistant.exposed_entities"] = exposed_mod
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["homeassistant.const"] = const_mod
    sys.modules["homeassistant.core"] = core_mod
    sys.modules["homeassistant.helpers"] = helpers_mod
    sys.modules["homeassistant.helpers.area_registry"] = ar_mod
    sys.modules["homeassistant.helpers.device_registry"] = dr_mod
    sys.modules["homeassistant.helpers.entity_registry"] = er_mod
    sys.modules["homeassistant.helpers.intent"] = intent_mod
    sys.modules["homeassistant.helpers.service"] = service_mod
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_mod
    sys.modules["homeassistant.helpers.entity_platform"] = ent_plat_mod


_install_ha_stubs()

REPO_ROOT = Path(__file__).resolve().parents[1]
CONV_PATH = (
    REPO_ROOT
    / "custom_components"
    / "system_1_2_dual_ai"
    / "conversation.py"
)
SPEC = importlib.util.spec_from_file_location("dual_ai_conversation", CONV_PATH)
assert SPEC and SPEC.loader
conv_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(conv_module)

DualModelConversationEntity = conv_module.DualModelConversationEntity
ConversationInput = sys.modules["homeassistant.components.conversation"].ConversationInput


def _make_state(entity_id: str, state: str, name: str, attributes: dict | None = None):
    st = MagicMock()
    st.entity_id = entity_id
    st.domain = entity_id.split(".", 1)[0]
    st.state = state
    st.name = name
    st.attributes = attributes or {}
    return st


class TestDualModelConversationEntity(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.hass = MagicMock()
        self.hass.services = MagicMock()
        self.hass.services.async_call = AsyncMock(return_value={})
        self.entity = DualModelConversationEntity(
            self.hass,
            "entry-1",
            {
                "sys1_provider": "OpenRouter",
                "sys1_model": "perplexity/pplx-decider-flash-v1.3:free",
                "sys2_provider": "OpenRouter",
                "sys2_model": "anthropic/claude-3.5-sonnet",
                "exposed_only": True,
                "control_granularity": "full",
            },
        )

    def test_build_choices_with_script_fields_and_weather(self) -> None:
        states = [
            _make_state("script.shuffle_playlist", "off", "Shuffle Playlist"),
            _make_state("script.my_eepy_time", "off", "Bed Time"),
            _make_state("weather.forecast_home", "sunny", "Forecast Home"),
        ]
        self.hass.states.async_all.return_value = states

        script_descriptions = {
            "shuffle_playlist": {
                "fields": {
                    "playlist_name": {"description": "Playlist name"},
                    "target_device": {"description": "Speaker name", "default": "Kitchen"},
                }
            }
        }

        with (
            patch.object(conv_module.er, "async_get", return_value=MagicMock(async_get=lambda eid: None)),
            patch.object(conv_module.dr, "async_get", return_value=MagicMock()),
            patch.object(conv_module.ar, "async_get", return_value=MagicMock()),
        ):
            choices = self.entity._build_choices_array(
                "Kitchen", "shuffle playlist", script_descriptions
            )

        self.assertIn(
            'EXECUTE script.shuffle_playlist (Shuffle Playlist) {"playlist_name": "", "target_device": "Kitchen"}',
            choices,
        )
        self.assertIn("EXECUTE script.my_eepy_time (Bed Time)", choices)
        self.assertIn("GET_WEATHER weather.forecast_home (Forecast Home)", choices)

    def test_parse_decision_script_and_weather(self) -> None:
        parsed_script = self.entity._parse_decision(
            'EXECUTE script.shuffle_playlist (Shuffle Playlist) {"playlist_name": "", "target_device": ""}',
            "shuffle my playlist in the kitchen",
        )
        self.assertEqual(parsed_script["domain"], "script")
        self.assertEqual(parsed_script["entity_id"], "script.shuffle_playlist")
        self.assertEqual(
            parsed_script["script_template"],
            {"playlist_name": "", "target_device": ""},
        )
        self.assertNotIn("music_query", parsed_script)

        parsed_weather = self.entity._parse_decision(
            "GET_WEATHER weather.forecast_home (Forecast Home)",
            "what is the weather like tomorrow?",
        )
        self.assertEqual(
            parsed_weather,
            {
                "domain": "weather",
                "service": "get_weather",
                "entity_id": "weather.forecast_home",
            },
        )

    async def test_parameterized_script_flow(self) -> None:
        script_state = _make_state("script.shuffle_playlist", "off", "Shuffle Playlist")
        self.hass.states.async_all.return_value = [script_state]
        self.hass.states.get.side_effect = lambda eid: script_state if eid == "script.shuffle_playlist" else None

        device = MagicMock(name="The-holy-dot", name_by_user=None, area_id="area-1")
        device.name = "The-holy-dot"
        area = MagicMock()
        area.name = "Peyton's Room"

        script_descriptions = {
            "shuffle_playlist": {
                "fields": {
                    "playlist_name": {"description": "Playlist name", "required": False},
                    "target_device": {"description": "Speaker name", "required": True},
                }
            }
        }

        llm_calls = []

        async def fake_call_llm(session, provider, model, sys_prompt, user_prompt, choices_list=None):
            llm_calls.append((sys_prompt, user_prompt, choices_list))
            if choices_list is not None:
                return 'EXECUTE script.shuffle_playlist (Shuffle Playlist) {"playlist_name": "", "target_device": ""}'
            return json.dumps(
                {
                    "parameters": {"playlist_name": "", "target_device": "Peyton's tablet"},
                    "reply": "Shuffling your playlist on Peyton's tablet.",
                }
            )

        with (
            patch.object(conv_module.service_helper, "async_get_all_descriptions", AsyncMock(return_value={"script": script_descriptions})),
            patch.object(conv_module.dr, "async_get", return_value=MagicMock(async_get=lambda did: device)),
            patch.object(conv_module.ar, "async_get", return_value=MagicMock(async_get_area=lambda aid: area)),
            patch.object(conv_module.er, "async_get", return_value=MagicMock(async_get=lambda eid: None)),
            patch.object(self.entity, "_call_llm", side_effect=fake_call_llm),
        ):
            result = await self.entity.async_process(
                ConversationInput(
                    text="Shuffle my playlist on Peyton's tablet",
                    device_id="dev-1",
                )
            )

        self.assertEqual(
            result.response.speech["plain"]["speech"],
            "Shuffling your playlist on Peyton's tablet.",
        )
        # Verify device & room were passed to both System 1 and System 2
        self.assertIn("Peyton's Room", llm_calls[0][0])
        self.assertIn("The-holy-dot", llm_calls[0][0])
        self.assertIn("Peyton's Room", llm_calls[1][0])
        self.assertIn("The-holy-dot", llm_calls[1][0])
        # Verify optional empty playlist_name was omitted and target_device was passed
        self.hass.services.async_call.assert_awaited_once_with(
            "script",
            "turn_on",
            {
                "entity_id": "script.shuffle_playlist",
                "variables": {"target_device": "Peyton's tablet"},
            },
            blocking=True,
        )

    async def test_weather_query_flow(self) -> None:
        weather_state = _make_state(
            "weather.forecast_home",
            "partlycloudy",
            "Forecast Home",
            {"temperature": 62, "temperature_unit": "°F"},
        )
        self.hass.states.async_all.return_value = [weather_state]
        self.hass.states.get.side_effect = lambda eid: weather_state if eid == "weather.forecast_home" else None

        async def fake_service_call(domain, service, data, blocking=True, return_response=False):
            if domain == "weather" and service == "get_forecasts":
                return {
                    "weather.forecast_home": {
                        "forecast": [
                            {"datetime": "2026-11-24", "condition": "partlycloudy", "temperature": 64},
                            {"datetime": "2026-11-25", "condition": "rainy", "temperature": 55},
                        ]
                    }
                }
            return {}

        self.hass.services.async_call = AsyncMock(side_effect=fake_service_call)
        llm_calls = []

        async def fake_call_llm(session, provider, model, sys_prompt, user_prompt, choices_list=None):
            llm_calls.append((sys_prompt, user_prompt, choices_list))
            if choices_list is not None:
                return "GET_WEATHER weather.forecast_home (Forecast Home)"
            return "Today is partly cloudy at 62°F, and tomorrow will be rainy with a high of 55°F."

        with (
            patch.object(conv_module.service_helper, "async_get_all_descriptions", AsyncMock(return_value={})),
            patch.object(conv_module.dr, "async_get", return_value=MagicMock(async_get=lambda did: None)),
            patch.object(conv_module.ar, "async_get", return_value=MagicMock()),
            patch.object(conv_module.er, "async_get", return_value=MagicMock(async_get=lambda eid: None)),
            patch.object(self.entity, "_call_llm", side_effect=fake_call_llm),
        ):
            result = await self.entity.async_process(
                ConversationInput(text="What is the weather like today and tomorrow?")
            )

        self.assertIn("partly cloudy", result.response.speech["plain"]["speech"])
        self.assertIn("Weather Data:", llm_calls[1][1])
        self.assertIn("rainy", llm_calls[1][1])


if __name__ == "__main__":
    unittest.main()
