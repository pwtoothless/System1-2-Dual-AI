import json
import logging
import datetime
from homeassistant.components import conversation
from homeassistant.helpers import intent, device_registry as dr, area_registry as ar
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.const import CONF_API_KEY, CONF_URL

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    config_data = dict(config_entry.data)
    config_data.update(config_entry.options)
    async_add_entities([DualModelConversationEntity(hass, config_data)])

class DualModelConversationEntity(conversation.ConversationEntity):
    _attr_has_entity_name = True
    _attr_name = "Echolocal Dual AI"
    _attr_supported_features = conversation.ConversationEntityFeature.CONTROL

    def __init__(self, hass, config_data):
        self.hass = hass
        self.config_data = config_data
        self.or_url = "https://openrouter.ai/api/v1/chat/completions"
        self.default_sys1 = "You are a smart home router. The user is in the '{room}'. If the command controls a device, match it to the exact entity_id below and return JSON with 'domain', 'service', and 'entity_id'. If it is a general question, return: {\"domain\": \"chat\", \"service\": \"chat\", \"entity_id\": \"none\"}\n\nAVAILABLE ENTITIES:\n{entities}\n\nOutput ONLY raw JSON. No markdown formatting."
        self.default_sys2 = "You are a helpful smart home AI. The current time is {time}. If the user asked a question, answer it concisely. If the user issued a device command, summarize the Action State into a natural, single-sentence spoken reply."

    @property
    def supported_languages(self) -> list[str] | str:
        return "*"

    async def _call_llm(self, session, provider, model, sys_prompt, user_prompt, is_json=False):
        if provider == "Ollama":
            url = self.config_data.get(CONF_URL)
            full_prompt = f"{sys_prompt}\n\n{user_prompt}"
            payload = {"model": model, "prompt": full_prompt, "stream": False, "options": {"temperature": 0.0}}
            if is_json: payload["format"] = "json"
            
            async with session.post(url, json=payload, timeout=20) as resp:
                res = await resp.json()
                if "error" in res: raise Exception(res["error"])
                return res.get("response", "").strip()
                
        elif provider == "OpenRouter":
            headers = {"Authorization": f"Bearer {self.config_data.get(CONF_API_KEY)}", "Content-Type": "application/json"}
            payload = {
                "model": model,
                "messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}],
                "temperature": 0.0
            }
            async with session.post(self.or_url, headers=headers, json=payload, timeout=10) as resp:
                res = await resp.json()
                if "error" in res: raise Exception(res["error"])
                text = res["choices"][0]["message"]["content"].strip()
                if is_json and text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"): text = text[4:]
                return text.strip()

    async def async_process(self, user_input: conversation.ConversationInput) -> conversation.ConversationResult:
        session = async_get_clientsession(self.hass)
        intent_response = intent.IntentResponse(language=user_input.language)
        
        # 1. Context & Entities
        room_context = "Unknown Area"
        if user_input.device_id:
            dev_reg = dr.async_get(self.hass)
            device = dev_reg.async_get(user_input.device_id)
            if device and device.area_id:
                area = ar.async_get(self.hass).async_get_area(device.area_id)
                if area: room_context = area.name

        valid_domains = {"light", "switch", "climate", "fan", "cover", "media_player", "script", "scene"}
        entities = [f"{s.name} = {s.entity_id}" for s in self.hass.states.async_all() if s.domain in valid_domains]
        entity_list_str = "\n".join(entities)

        # 2. System 1: Decision Model
        sys1_template = self.config_data.get("sys1_prompt", self.default_sys1)
        sys1_prompt = sys1_template.replace("{room}", room_context).replace("{entities}", entity_list_str)
        
        try:
            raw_response = await self._call_llm(
                session, 
                self.config_data.get("sys1_provider"), 
                self.config_data.get("sys1_model"), 
                sys1_prompt, 
                f"Command: \"{user_input.text}\"", 
                is_json=True
            )
            action_data = json.loads(raw_response)
        except Exception as e:
            _LOGGER.error("System 1 Error: %s", e)
            intent_response.async_set_speech("The decision model failed to respond.")
            return conversation.ConversationResult(response=intent_response, conversation_id=user_input.conversation_id)

        # 3. Execute Action Natively
        domain = action_data.get("domain")
        service = action_data.get("service")
        entity_id = action_data.get("entity_id")
        
        # Build service data and inject custom LLM variables (e.g., music_query)
        service_data = {}
        if entity_id and entity_id.lower() != "none":
            service_data["entity_id"] = entity_id
            
        for key, value in action_data.items():
            if key not in ["domain", "service", "entity_id"]:
                service_data[key] = value

        action_state = {"status": "skipped", "message": "User asked a general question."}
        
        if domain != "chat" and domain and service:
            try:
                await self.hass.services.async_call(domain, service, service_data, blocking=True)
                action_state = {"status": "success", "action": f"{service} executed"}
            except Exception as e:
                action_state = {"status": "error", "message": str(e)}

        # 4. System 2: Conversational Model
        current_time = datetime.datetime.now().strftime("%I:%M %p on %A, %B %d")
        sys2_template = self.config_data.get("sys2_prompt", self.default_sys2)
        sys2_prompt = sys2_template.replace("{time}", current_time)

        if action_data.get("domain") == "chat":
            sys2_user = user_input.text
        else:
            sys2_user = f"User Command: \"{user_input.text}\"\nAction State: {json.dumps(action_state)}"
        
        try:
            spoken_reply = await self._call_llm(
                session, 
                self.config_data.get("sys2_provider"), 
                self.config_data.get("sys2_model"), 
                sys2_prompt, 
                sys2_user
            )
        except Exception as e:
            _LOGGER.error("System 2 Error: %s", e)
            spoken_reply = "Action completed, but the reply generator failed."

        # 5. Return Text to TTS Engine
        intent_response.async_set_speech(spoken_reply)
        return conversation.ConversationResult(response=intent_response, conversation_id=user_input.conversation_id)