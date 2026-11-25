# System 1 & 2 Dual AI for Home Assistant 

A dual-model conversation agent for Home Assistant's Assist voice and chat pipelines.

By splitting each turn into a **System 1 Decision Engine** (fast, deterministic intent-to-entity routing) and a **System 2 Conversational Engine** (natural spoken/text reply generation), this integration avoids the high latency, token bloat, and tool-calling hallucinations of single-LLM smart home assistants.

[![Open your Home Assistant instance and open a repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=pwtoothless&category=Intigration&repository=System1-2-Dual-AI)

---

## How It Works

```text
User Command ("Turn on Desk LED's in Peytons Room")
   │
   ▼
[1. Context & Choice Builder]
   • Resolves originating speaker's Area ({room})
   • Collects available entities (excluding unavailable/unknown)
   • Filters to Assist-exposed entities only (default)
   • Builds action choices according to Device Control Granularity
   • Prioritizes by exposure, room, and query keywords (capped at 255 for Decisions API)
   │
   ▼
[2. System 1 — Fast Router]
   • Selects either "CHAT" or a single exact action (e.g., "TURN_ON light.desk_leds (Desk LEDs - Peytons Room)")
   │
   ├──► If "CHAT" ──────────────────────────────────────────────┐
   │                                                            ▼
   └──► If Device Action ──► [3. Home Assistant Service Call] ──► [4. System 2 — Responder]
                              • Verifies entity is available     • Summarizes Action State or answers
                              • Calls domain.service               general questions using {time}
                              • Passes music_query to scripts    • Returns final Assist response
```

---

## Features

- **Hybrid Provider Routing:** Mix and match **Ollama** (local) and **OpenRouter** (cloud) independently for System 1 and System 2.
- **Native OpenRouter Decisions API Support:** Automatically routes decision models (`perplexity/pplx-decider*`, `liquid/d1.1`, `typesafe/*`, or any model containing `decider`/`decision`) to OpenRouter's `/api/alpha/decisions` endpoint using the structured `state` + `questions` schema.
- **Security-First Default (`Assist-Exposed Entities Only`):** Enabled by default so System 1 can only see and control entities you explicitly expose under **Settings → Voice Assistants → Expose**.
- **Configurable Device Control Granularity:** Choose between **Full**, **Compact**, and **Minimal (State-Aware)** action sets to stay comfortably within OpenRouter's **255-option** per-decision limit.
- **Availability Guard & Smart Matching:** Automatically excludes `unavailable` / `unknown` entities from choices, verifies availability before calling services, normalizes curly apostrophes/quotes (e.g., `Desk LED’s` → `Desk LED's`), and includes each entity's Area name in its choice label.
- **Script Parameter Forwarding (Auto-Discovered Fields):** Automatically inspects Home Assistant script `fields` and includes pre-filled JSON parameter templates in System 1's choices. When System 1 selects a parameterized script, System 2 fills in the parameters from your original prompt (using `{room}` and `{device}` context) and executes the script with those variables.
- **Weather & Forecast Support:** Includes Assist-exposed `weather.*` entities as `GET_WEATHER` choices in System 1, automatically fetching current conditions plus `daily` and `hourly` forecasts (`weather.get_forecasts`) for System 2 to answer today/tomorrow weather questions.
- **Originating Device & Room Context:** Resolves both the speaking satellite device (`{device}`) and its area (`{room}`) from `device_id` and passes them to both System 1 and System 2.
- **Light Brightness, Color & White Temperature:** Extracts percentage brightness (`brightness_pct`), warm/cool white presets (`color_temp_kelvin`), and named RGB colors (`rgb_color`) directly from your command when turning on lights—without adding extra choices to the 255-option decision budget.
- **Live Options Flow:** Update providers, models, prompts, security scope, granularity, and credentials from the UI at any time without removing the integration.

---

## Light Controls (Brightness, Color, Warm & Cool White)

System 1 only needs to select `TURN_ON <light.entity>`—it does **not** need separate options in the 255-choice list for every brightness level or color. When `light.turn_on` is executed, the integration parses supported light attributes from your command and checks the target light's `supported_color_modes` before applying them:

- **Brightness:** Any explicit percentage (`"50%"`, `"75 percent"`, `"0%"`–`"100%"`) → `brightness_pct`
- **Warm & Cool White (`color_temp_kelvin`):**
  - `"warm white"` → `2700 K`
  - `"soft white"` → `3000 K`
  - `"neutral white"` → `4000 K`
  - `"daylight"` → `4500 K`
  - `"cool white"` → `5500 K`
- **Named Colors (`rgb_color`):** `"red"`, `"green"`, `"blue"`, `"yellow"`, `"orange"`, `"purple"`, `"pink"`, `"cyan"`, `"teal"`, `"magenta"`, `"white"`

> **Note:** Arbitrary hex codes, relative adjustments (`"a little brighter"`), and multi-light commands in a single turn are not currently parsed; use explicit percentages, preset white temperatures, or named colors.

---

## Supported Entity Domains

| Domain | Full Mode Actions | Compact Mode Actions | Minimal (State-Aware) Actions |
| :--- | :--- | :--- | :--- |
| `light`, `switch`, `climate`, `fan`, `media_player` | `TURN_ON`, `TURN_OFF`, `TOGGLE` | `TURN_ON`, `TURN_OFF` | `TURN_OFF` (if `on`) or `TURN_ON` (if `off`) |
| `cover` | `OPEN`, `CLOSE` | `OPEN`, `CLOSE` | `CLOSE` (if `open`) or `OPEN` (if `closed`) |
| `script`, `scene` | `EXECUTE` (with pre-filled JSON template for parameterized scripts) | `EXECUTE` | `EXECUTE` |
| `weather` | `GET_WEATHER` | `GET_WEATHER` | `GET_WEATHER` |

---

## Installation

### Option 1: HACS (Recommended)
1. Open Home Assistant and go to **HACS → Integrations**.
2. Click the three-dot menu (**⋮**) in the top-right corner and select **Custom repositories**.
3. Add this repository's URL and select **Integration** as the category.
4. Search for **System 1 & 2 Dual AI**, click **Download**, and restart Home Assistant.

### Option 2: Manual Installation
1. Copy `custom_components/system_1_2_dual_ai` into your Home Assistant `/config/custom_components/` directory.
2. Restart Home Assistant.

---

## Configuration

1. Go to **Settings → Devices & Services → + Add Integration** and search for **System 1 & 2 Dual AI**.
2. **Step 1 — Select AI Providers:**
   - Choose `Ollama` or `OpenRouter` for **System 1 Provider (Router)**.
   - Choose `Ollama` or `OpenRouter` for **System 2 Provider (Responder)**.
3. **Step 2 — Configure Models & Credentials:**
   - **System 1 Model:** e.g. `perplexity/pplx-decider-flash-v1.3:free` (OpenRouter) or `tev1-4b-decision` (Ollama).
   - **System 1 Prompt:** Supports `{room}` (resolved from the triggering Assist device's Area).
   - **System 2 Model:** e.g. `anthropic/claude-3.5-sonnet`, `google/gemini-2.0-flash-001`, or a local Ollama model.
   - **System 2 Prompt:** Supports `{time}` (current local time and date).
   - **Assist-Exposed Entities Only:** Checked (`true`) by default for security.
   - **Device Control Granularity:** Choose `Full`, `Compact`, or `Minimal (State-aware single action)`.
   - **OpenRouter API Key** (shown if either provider is OpenRouter) / **Ollama Generate URL** (shown if either provider is Ollama).
4. **Assign to a Voice Assistant:**
   - Go to **Settings → Voice Assistants**, create or edit an assistant, and set **Conversation agent** to **System 1 & 2 Dual AI**.

You can update any of these settings later by clicking **Configure** on the integration card.

---

## Device Control Granularity (255-Option Limit)

OpenRouter's `/api/alpha/decisions` endpoint enforces a hard limit of **255 options per decision**. Because 1 option is always reserved for `CHAT` (general questions), **254 slots** remain for device actions.

If your smart home exceeds 255 total options, the integration automatically scores and prioritizes choices in this order before applying the 255-option cap:
1. **Assist-exposed entities** (`+100` priority)
2. **Query keyword matches** (`+30` per matching word from your command)
3. **Current room / area matches** (`+20` if the entity is in `{room}`)

To keep all of your devices within the 255-option budget without relying on truncation, choose the **Device Control Granularity** that matches your exposed device count:

| Exposed Devices | Recommended Level | Actions / Device | Max Devices Under 255 |
| :--- | :--- | :--- | :--- |
| **1 – 80** | **Full (`On / Off / Toggle`)** | 3 (`2` for covers, `1` for scripts/scenes) | ~84 |
| **81 – 125** | **Compact (`On / Off`)** | 2 (`1` for scripts/scenes) | ~127 |
| **126 – 254** | **Minimal (State-aware single action)** | 1 | 254 |
| **255+** | **Minimal + Assist-Exposed Only** | 1 | 254 active per turn |

### Pros and Cons of Each Level

#### 1. Full (`On / Off / Toggle`) — Default
Generates `TURN_ON`, `TURN_OFF`, and `TOGGLE` for each controllable entity.
- **Pros:**
  - Supports every standard voice phrasing, including explicit `"toggle the kitchen light"` commands.
  - Works reliably even if a device's reported state in Home Assistant is momentarily stale.
- **Cons:**
  - Uses 3 option slots per device, capping out around **84 devices** under the 255-option limit.
  - Higher prompt/choice token count per request.

#### 2. Compact (`On / Off`)
Generates only `TURN_ON` and `TURN_OFF` (omitting `TOGGLE`).
- **Pros:**
  - Increases capacity by **50%** (up to **~127 devices**) while preserving explicit on/off control.
  - Reduces ambiguity for System 1 when choosing between `TURN_ON` and `TOGGLE`.
  - Lower token usage than Full mode.
- **Cons:**
  - Commands that literally ask to `"toggle"` a device will map to `TURN_ON` or `TURN_OFF` instead of `toggle`.

#### 3. Minimal (`State-aware single action`)
Inspects each entity's current state and generates only the opposite action (`TURN_OFF` if currently `on`, `TURN_ON` if currently `off`; `CLOSE` if `open`, `OPEN` if `closed`).
- **Pros:**
  - Maximum capacity: fits up to **254 devices** under the 255-option limit.
  - Lowest token count and fastest routing among all modes.
  - Prevents redundant calls (e.g., turning on a light that is already on).
- **Cons:**
  - If an entity's state in Home Assistant is out of sync with the physical device (e.g., a bulb is physically off but HA still shows `on`), saying `"turn on the light"` will not have a `TURN_ON` choice available.
  - Does not offer `TOGGLE`.

---

## Security: Assist-Exposed Entities Only

By default, **Assist-Exposed Entities Only** is **enabled (`true`)**.
- **Why:** Prevents System 1 from seeing or acting on sensitive or unexposed entities (such as garage doors, locks, switches for servers/routers, or internal helper scripts) unless you explicitly expose them in **Settings → Voice Assistants → Expose**.
- **When to disable:** Only uncheck this if you intentionally want the LLM to have access to every available entity in the supported domains across your entire Home Assistant instance.

---

## Troubleshooting

- **"The decision model failed to respond."**
  - Check **Settings → System → Logs** for `custom_components.system_1_2_dual_ai.conversation`.
  - Verify your OpenRouter API key or Ollama URL in **Configure**.
  - If using Ollama, ensure the endpoint ends with `/api/generate` and is reachable from the Home Assistant container.
- **"Action completed, but the reply generator failed."**
  - System 1 succeeded, but System 2 failed. Common causes:
    - **HTTP 404:** The configured System 2 model was deprecated or removed on OpenRouter—switch to an active model in **Configure**.
    - **HTTP 429:** A `:free` OpenRouter model hit an upstream shared rate limit—retry shortly or switch to a paid/BYOK or local Ollama model.
- **Assistant says a device was turned on, but nothing happened:**
  - Ensure the target entity is not `unavailable` in Home Assistant and is exposed to Assist (when **Assist-Exposed Entities Only** is enabled).
