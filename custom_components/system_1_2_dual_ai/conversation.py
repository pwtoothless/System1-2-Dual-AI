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
    _attr_name = "System 1 & 2 Dual AI"
    _attr_supported_features = conversation.ConversationEntityFeature.CONTROL

    def __init__(self, hass, config_data):
        self.hass = hass
        self.config_data = config_data
        self.default_sys1 = "You are a smart home router. The user is in the '{room}'. Pick the most appropriate action from the choices to fulfill the command. If the user asks a general question, select 'CHAT'."
        self.default_sys2 = "You are a helpful smart home AI. The current time is {time}. If the user asked a question, answer it concisely. If the user issued a device command, summarize the Action State into a natural, single-sentence spoken reply."

    @property
    def supported_languages(self) -> list[str] | str:
        return "*"

    async def _call_llm(self, session, provider, model, sys_prompt, user_prompt, choices_list=None):
        if provider == "Ollama":
            url = self.config_data.get(CONF_URL)
            full_prompt = f"{sys_prompt}\n\n{user_prompt}"
            if choices_list:
                full_prompt += "\n\nAVAILABLE CHOICES:\n" + "\n".join(choices_list) + "\n\nReply ONLY with the exact text of one of the choices above."
            
            payload = {"model": model, "prompt": full_prompt, "stream": False, "options": {"temperature": 0.0}}
            async with session.post(url, json=payload, timeout=20) as resp:
                res = await resp.json()
                if "error" in res: raise Exception(res["error"])
                return res.get("response", "").strip()
                
        elif provider == "OpenRouter":
            headers = {"Authorization": f"Bearer {self.config_data.get(CONF_API_KEY)}", "Content-Type": "application/json"}
            
            if model in ["liquid/d1.1"] or model.startswith("typesafe/"):
                api_url = "https://openrouter.ai/api/alpha/decisions"
                payload = {
                    "model": model,
                    "messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]
                }
                if choices_list:
                    payload["choices"] = choices_list
            else:
                api_url = "https://openrouter.ai/api/v1/chat/completions"
                sys_prompt_final = sys_prompt
                if choices_list:
                    sys_prompt_final += "\n\nAVAILABLE CHOICES:\n" + "\n".join(choices_list) + "\n\nReply ONLY with the exact text of one of the choices above."
                    
                payload = {
                    "model": model,
                    "messages": [{"role": "system", "content": sys_prompt_final}, {"role": "user", "content": user_prompt}],
                    "temperature": 0.0
                }

            async with session.post(api_url, headers=headers, json=payload, timeout=10) as resp:
                res = await resp.json()
                if "error" in res: raise Exception(str(res["error"]))
                return res["choices"][0]["message"]["content"].strip()

    async def async_process(self, user_input: conversation.ConversationInput) -> conversation.ConversationResult:
        session = async_get_clientsession(self.hass)
        intent_response = intent.IntentResponse(language=user_input.language)
        
        # 1. Context
        room_context = "Unknown Area"
        if user_input.device_id:
            dev_reg = dr.async_get(self.hass)
            device = dev_reg.async_get(user_input.device_id)
            if device and device.area_id:
                area = ar.async_get(self.hass).async_get_area(device.area_id)
                if area: room_context = area.name

        # 2. Build the Decision Choices Array
        valid_domains = {"light", "switch", "climate", "fan", "cover", "media_player", "script", "scene"}
        choices_array = ["CHAT"]
        for s in self.hass.states.async_all():
            if s.domain in valid_domains:
                name = s.name.replace('"', '').replace("'", "")
                eid = s.entity_id
                if s.domain in ["script", "scene"]:
                    choices_array.append(f"EXECUTE {eid} ({name})")
                elif s.domain in ["cover"]:
                    choices_array.append(f"OPEN {eid} ({name})")
                    choices_array.append(f"CLOSE {eid} ({name})")
                else:
                    choices_array.append(f"TURN_ON {eid} ({name})")
                    choices_array.append(f"TURN_OFF {eid} ({name})")
                    choices_array.append(f"TOGGLE {eid} ({name})")

        sys1_template = self.config_data.get("sys1_prompt", self.default_sys1)
        sys1_prompt = sys1_template.replace("{room}", room_context).replace("{entities}", "")
        
        try:
            decision = await self._call_llm(
                session, 
                self.config_data.get("sys1_provider"), 
                self.config_data.get("sys1_model"), 
                sys1_prompt, 
                f"Command: \"{user_input.text}\"", 
                choices_list=choices_array
            )
            
            # Parse the Choice
            action_data = {}
            if not decision or decision == "CHAT" or "CHAT" in decision:
                action_data = {"domain": "chat", "service": "chat", "entity_id": "none"}
            else:
                parts = decision.split(" ")
                action = parts[0]
                entity_id = parts[1] if len(parts) > 1 else "none"
                domain = entity_id.split(".")[0] if "." in entity_id else "chat"
                
                if action == "TURN_ON": service = "turn_on"
                elif action == "TURN_OFF": service = "turn_off"
                elif action == "TOGGLE": service = "toggle"
                elif action == "OPEN": service = "open_cover"
                elif action == "CLOSE": service = "close_cover"
                elif action == "EXECUTE": service = "turn_on"
                else: service = "turn_on"
                
                action_data = {"domain": domain, "service": service, "entity_id": entity_id}
                
                # Automatically map the raw voice transcript to 'music_query' for media scripts
                action_data["music_query"] = user_input.text
                
        except Exception as e:
            _LOGGER.error("System 1 Error: %s", e)
            intent_response.async_set_speech("The decision model failed to respond.")
            return conversation.ConversationResult(response=intent_response, conversation_id=user_input.conversation_id)

        # 3. Execute Action
        domain = action_data.get("domain")
        service = action_data.get("service")
        entity_id = action_data.get("entity_id")
        
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
                action_state = {"status": "success", "action": f"{service} {entity_id}"}
            except Exception as e:
                action_state = {"status": "error", "message": str(e)}

        # 4. System 2 Request
        current_time = datetime.datetime.now().strftime("%I:%M %p on %A, %B %d")
        sys2_template = self.config_data.get("sys2_prompt", self.default_sys2)
        sys2_prompt = sys2_template.replace("{time}", current_time)

        if action_data.get("domain") == "chat":
            sys2_user = user_input.text
        else:
            sys2_user = f"User Command: \"{user_input.text}\"\nAction State: {json.dumps(action_state)}\nDecision Array Output: {decision}"
        
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

        intent_response.async_set_speech(spoken_reply)
        return conversation.ConversationResult(response=intent_response, conversation_id=user_input.conversation_id)