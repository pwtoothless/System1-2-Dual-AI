"""Conversation entity for System 1 & 2 Dual AI."""

from __future__ import annotations

import datetime
import json
import logging
import re
from typing import Any

import aiohttp

from homeassistant.components import conversation
from homeassistant.components.homeassistant.exposed_entities import async_should_expose
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    intent,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)

VALID_DOMAINS = {
    "light",
    "switch",
    "climate",
    "fan",
    "cover",
    "media_player",
    "script",
    "scene",
}

ACTION_SERVICE_MAP = {
    "TURN_ON": "turn_on",
    "TURN_OFF": "turn_off",
    "TOGGLE": "toggle",
    "OPEN": "open_cover",
    "CLOSE": "close_cover",
    "EXECUTE": "turn_on",
}

MAX_DECISION_CHOICES = 255

COLOR_TEMP_PRESETS_KELVIN: dict[str, int] = {
    "warm white": 2700,
    "soft white": 3000,
    "neutral white": 4000,
    "daylight": 4500,
    "cool white": 5500,
}

RGB_COLOR_PRESETS: dict[str, tuple[int, int, int]] = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "orange": (255, 165, 0),
    "purple": (128, 0, 128),
    "pink": (255, 105, 180),
    "cyan": (0, 255, 255),
    "teal": (0, 128, 128),
    "magenta": (255, 0, 255),
    "white": (255, 255, 255),
}


def _normalize_text(text: str) -> str:
    """Normalize curly quotes/apostrophes and whitespace for matching."""
    return (
        text.replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .strip()
    )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the System 1 & 2 Dual AI conversation entity."""
    config_data = dict(config_entry.data)
    config_data.update(config_entry.options)
    async_add_entities(
        [DualModelConversationEntity(hass, config_entry.entry_id, config_data)]
    )


class DualModelConversationEntity(conversation.ConversationEntity):
    """Dual-model (System 1 router + System 2 responder) conversation entity."""

    _attr_has_entity_name = True
    _attr_name = "System 1 & 2 Dual AI"
    _attr_supported_features = conversation.ConversationEntityFeature.CONTROL

    def __init__(
        self, hass: HomeAssistant, entry_id: str, config_data: dict[str, Any]
    ) -> None:
        """Initialize the conversation entity."""
        self.hass = hass
        self._attr_unique_id = entry_id
        self.config_data = config_data
        self.default_sys1 = (
            "You are a smart home router. The user is in the '{room}'. "
            "Pick the most appropriate action from the choices to fulfill the command. "
            "If the user asks a general question, select 'CHAT'."
        )
        self.default_sys2 = (
            "You are a helpful smart home AI. The current time is {time}. "
            "If the user asked a question, answer it concisely. "
            "If the user issued a device command, summarize the Action State into a natural, "
            "single-sentence spoken reply."
        )

    @property
    def supported_languages(self) -> list[str] | str:
        """Return supported languages."""
        return "*"

    async def _call_llm(
        self,
        session: aiohttp.ClientSession,
        provider: str | None,
        model: str | None,
        sys_prompt: str,
        user_prompt: str,
        choices_list: list[str] | None = None,
    ) -> str:
        """Call the configured LLM provider and return the text response."""
        if not provider or not model:
            raise ValueError("LLM provider and model must be configured")

        if provider == "Ollama":
            url = self.config_data.get(CONF_URL)
            if not url:
                raise ValueError("Ollama URL is not configured")

            full_prompt = f"{sys_prompt}\n\n{user_prompt}"
            if choices_list:
                full_prompt += (
                    "\n\nAVAILABLE CHOICES:\n"
                    + "\n".join(choices_list)
                    + "\n\nReply ONLY with the exact text of one of the choices above."
                )

            payload = {
                "model": model,
                "prompt": full_prompt,
                "stream": False,
                "options": {"temperature": 0.0},
            }
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    raise RuntimeError(f"Ollama HTTP {resp.status}: {body[:200]}")
                res = await resp.json()
                if "error" in res:
                    raise RuntimeError(str(res["error"]))
                return str(res.get("response", "")).strip()

        if provider == "OpenRouter":
            api_key = self.config_data.get(CONF_API_KEY)
            if not api_key:
                raise ValueError("OpenRouter API key is not configured")

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            is_decisions_model = (
                model in ("liquid/d1.1",)
                or model.startswith("typesafe/")
                or "decider" in model.lower()
                or "decision" in model.lower()
            )
            if is_decisions_model:
                api_url = "https://openrouter.ai/api/alpha/decisions"
                if choices_list:
                    capped = choices_list[:MAX_DECISION_CHOICES]
                    criteria = {choice: choice for choice in capped}
                else:
                    criteria = {"CHAT": "General question or conversation"}
                payload: dict[str, Any] = {
                    "model": model,
                    "state": {"command": user_prompt},
                    "questions": {
                        "action": {
                            "type": "choice",
                            "instructions": sys_prompt,
                            "criteria": criteria,
                        }
                    },
                }
            else:
                api_url = "https://openrouter.ai/api/v1/chat/completions"
                sys_prompt_final = sys_prompt
                if choices_list:
                    sys_prompt_final += (
                        "\n\nAVAILABLE CHOICES:\n"
                        + "\n".join(choices_list)
                        + "\n\nReply ONLY with the exact text of one of the choices above."
                    )

                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": sys_prompt_final},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.0,
                }

            async with session.post(
                api_url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    raise RuntimeError(f"OpenRouter HTTP {resp.status}: {body[:500]}")
                res = await resp.json()
                if "error" in res:
                    raise RuntimeError(str(res["error"]))
                if is_decisions_model:
                    decisions = res.get("decisions") or res.get("answers") or {}
                    action_res = decisions.get("action")
                    if isinstance(action_res, dict):
                        if "choice" in action_res:
                            return str(action_res["choice"]).strip()
                        if "value" in action_res:
                            return str(action_res["value"]).strip()
                    if isinstance(action_res, str):
                        return action_res.strip()
                    raise RuntimeError(f"Unexpected decisions response: {res}")
                choices = res.get("choices") or []
                if not choices:
                    raise RuntimeError("OpenRouter returned no choices")
                return str(choices[0]["message"]["content"]).strip()

        raise ValueError(f"Unsupported provider: {provider}")

    def _resolve_room_context(self, device_id: str | None) -> str:
        """Resolve the area name for the originating device."""
        if not device_id:
            return "Unknown Area"
        device = dr.async_get(self.hass).async_get(device_id)
        if device and device.area_id:
            area = ar.async_get(self.hass).async_get_area(device.area_id)
            if area:
                return _normalize_text(area.name)
        return "Unknown Area"

    def _get_entity_area_name(
        self,
        entity_id: str,
        ent_reg: er.EntityRegistry,
        dev_reg: dr.DeviceRegistry,
        area_reg: ar.AreaRegistry,
    ) -> str | None:
        """Return the normalized area name for an entity, if assigned."""
        ent_entry = ent_reg.async_get(entity_id)
        if not ent_entry:
            return None
        area_id = ent_entry.area_id
        if not area_id and ent_entry.device_id:
            device = dev_reg.async_get(ent_entry.device_id)
            if device:
                area_id = device.area_id
        if area_id:
            area = area_reg.async_get_area(area_id)
            if area:
                return _normalize_text(area.name)
        return None

    def _build_choices_array(
        self, room_context: str, user_text: str
    ) -> list[str]:
        """Build prioritized, available entity action choices for System 1."""
        ent_reg = er.async_get(self.hass)
        dev_reg = dr.async_get(self.hass)
        area_reg = ar.async_get(self.hass)

        query_tokens = {
            tok
            for tok in re.findall(r"[a-z0-9]+", _normalize_text(user_text).lower())
            if len(tok) >= 3
        }
        room_lower = room_context.lower()

        exposed_only = self.config_data.get("exposed_only", True)
        granularity = self.config_data.get("control_granularity", "full")

        scored_choices: list[tuple[int, str]] = []

        for state in self.hass.states.async_all():
            if state.domain not in VALID_DOMAINS:
                continue
            if state.state in ("unavailable", "unknown"):
                continue

            eid = state.entity_id
            try:
                exposed = async_should_expose(self.hass, conversation.DOMAIN, eid)
            except Exception:
                exposed = True

            if exposed_only and not exposed:
                continue

            name = _normalize_text(state.name).replace('"', "").replace("'", "")
            area_name = self._get_entity_area_name(eid, ent_reg, dev_reg, area_reg)
            label = f"{name} - {area_name}" if area_name else name

            # Score relevance so the 255-option cap never drops target entities.
            score = 0
            if exposed:
                score += 100
            label_lower = f"{label} {eid}".lower().replace("'", "")
            if area_name and area_name.lower() == room_lower:
                score += 20
            for tok in query_tokens:
                if tok in label_lower:
                    score += 30

            if state.domain in ("script", "scene"):
                scored_choices.append((score, f"EXECUTE {eid} ({label})"))
            elif state.domain == "cover":
                if granularity == "state_aware":
                    action = "CLOSE" if state.state == "open" else "OPEN"
                    scored_choices.append((score, f"{action} {eid} ({label})"))
                else:
                    scored_choices.append((score, f"OPEN {eid} ({label})"))
                    scored_choices.append((score, f"CLOSE {eid} ({label})"))
            elif granularity == "state_aware":
                action = "TURN_OFF" if state.state == "on" else "TURN_ON"
                scored_choices.append((score, f"{action} {eid} ({label})"))
            elif granularity == "compact":
                scored_choices.append((score, f"TURN_ON {eid} ({label})"))
                scored_choices.append((score, f"TURN_OFF {eid} ({label})"))
            else:
                scored_choices.append((score, f"TURN_ON {eid} ({label})"))
                scored_choices.append((score, f"TURN_OFF {eid} ({label})"))
                scored_choices.append((score, f"TOGGLE {eid} ({label})"))

        scored_choices.sort(key=lambda item: item[0], reverse=True)
        return ["CHAT"] + [choice for _, choice in scored_choices]

    def _parse_decision(self, decision: str, raw_text: str) -> dict[str, Any]:
        """Parse System 1's selected choice into a service call dict."""
        cleaned = (decision or "").strip()
        if not cleaned or cleaned.upper() == "CHAT":
            return {"domain": "chat", "service": "chat", "entity_id": "none"}

        parts = cleaned.split(" ")
        action = parts[0].upper()
        entity_id = parts[1] if len(parts) > 1 else "none"
        domain = entity_id.split(".")[0] if "." in entity_id else "chat"
        service = ACTION_SERVICE_MAP.get(action, "turn_on")

        action_data: dict[str, Any] = {
            "domain": domain,
            "service": service,
            "entity_id": entity_id,
        }
        # Only pass music_query to scripts so standard domains (light, switch, etc.)
        # do not fail schema validation with extra keys.
        if domain == "script":
            action_data["music_query"] = raw_text

        return action_data

    def _extract_light_attributes(
        self, raw_text: str, target_state: Any
    ) -> dict[str, Any]:
        """Extract brightness, color temp, and RGB color from user text if supported."""
        text_lower = _normalize_text(raw_text).lower()
        attrs: dict[str, Any] = {}
        supported_modes = set(
            target_state.attributes.get("supported_color_modes") or []
        )

        # Brightness percentage (e.g., "50%", "75 percent")
        pct_match = re.search(r"\b(100|[1-9]?\d)\s*(?:%|percent\b)", text_lower)
        if pct_match and (
            not supported_modes
            or supported_modes - {"onoff"}
        ):
            attrs["brightness_pct"] = int(pct_match.group(1))

        # Warm / cool white color temperature presets
        temp_matched = False
        if not supported_modes or "color_temp" in supported_modes:
            for phrase, kelvin in COLOR_TEMP_PRESETS_KELVIN.items():
                if re.search(rf"\b{re.escape(phrase)}\b", text_lower):
                    attrs["color_temp_kelvin"] = kelvin
                    temp_matched = True
                    break

        # Named RGB colors (skip "white" if a color-temp phrase already matched)
        color_modes = {"rgb", "rgbw", "rgbww", "hs", "xy"}
        if not temp_matched and (
            not supported_modes or bool(supported_modes & color_modes)
        ):
            for color_name, rgb in RGB_COLOR_PRESETS.items():
                if re.search(rf"\b{re.escape(color_name)}\b", text_lower):
                    attrs["rgb_color"] = list(rgb)
                    break

        return attrs

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        """Process a user conversation turn."""
        session = async_get_clientsession(self.hass)
        intent_response = intent.IntentResponse(language=user_input.language)

        room_context = self._resolve_room_context(user_input.device_id)
        choices_array = self._build_choices_array(room_context, user_input.text)

        sys1_template = self.config_data.get("sys1_prompt", self.default_sys1)
        sys1_prompt = sys1_template.replace("{room}", room_context).replace(
            "{entities}", ""
        )

        try:
            decision = await self._call_llm(
                session,
                self.config_data.get("sys1_provider"),
                self.config_data.get("sys1_model"),
                sys1_prompt,
                f'Command: "{user_input.text}"',
                choices_list=choices_array,
            )
            _LOGGER.debug("System 1 decision: %s", decision)
            action_data = self._parse_decision(decision, user_input.text)
        except Exception as err:
            _LOGGER.error("System 1 Error: %s", err)
            intent_response.async_set_speech("The decision model failed to respond.")
            return conversation.ConversationResult(
                response=intent_response, conversation_id=user_input.conversation_id
            )

        domain = action_data.get("domain")
        service = action_data.get("service")
        entity_id = action_data.get("entity_id")

        service_data: dict[str, Any] = {}
        if entity_id and str(entity_id).lower() != "none":
            service_data["entity_id"] = entity_id

        for key, value in action_data.items():
            if key not in ("domain", "service", "entity_id"):
                service_data[key] = value

        action_state: dict[str, Any] = {
            "status": "skipped",
            "message": "User asked a general question.",
        }

        if domain != "chat" and domain and service:
            target_state = self.hass.states.get(entity_id) if entity_id else None
            if target_state is None or target_state.state in ("unavailable", "unknown"):
                action_state = {
                    "status": "error",
                    "message": f"Target entity {entity_id} is unavailable.",
                }
                _LOGGER.warning("Skipping service call; %s is unavailable", entity_id)
            else:
                if domain == "light":
                    light_attrs = self._extract_light_attributes(
                        user_input.text, target_state
                    )
                    if light_attrs:
                        # In state_aware mode, an already-on light only offers TURN_OFF;
                        # if the user asked for brightness/color/temp, apply via turn_on.
                        if service == "turn_off" and not re.search(
                            r"\boff\b", user_input.text.lower()
                        ):
                            service = "turn_on"
                        if service == "turn_on":
                            service_data.update(light_attrs)
                try:
                    await self.hass.services.async_call(
                        domain, service, service_data, blocking=True
                    )
                    action_state = {
                        "status": "success",
                        "action": f"{service} {entity_id}",
                    }
                except Exception as err:
                    _LOGGER.warning(
                        "Service call %s.%s failed for %s: %s",
                        domain,
                        service,
                        entity_id,
                        err,
                    )
                    action_state = {"status": "error", "message": str(err)}

        current_time = datetime.datetime.now().strftime("%I:%M %p on %A, %B %d")
        sys2_template = self.config_data.get("sys2_prompt", self.default_sys2)
        sys2_prompt = sys2_template.replace("{time}", current_time)

        if domain == "chat":
            sys2_user = user_input.text
        else:
            sys2_user = (
                f'User Command: "{user_input.text}"\n'
                f"Action State: {json.dumps(action_state)}\n"
                f"Decision Array Output: {decision}"
            )

        try:
            spoken_reply = await self._call_llm(
                session,
                self.config_data.get("sys2_provider"),
                self.config_data.get("sys2_model"),
                sys2_prompt,
                sys2_user,
            )
        except Exception as err:
            _LOGGER.error("System 2 Error: %s", err)
            spoken_reply = "Action completed, but the reply generator failed."

        intent_response.async_set_speech(spoken_reply)
        return conversation.ConversationResult(
            response=intent_response, conversation_id=user_input.conversation_id
        )
