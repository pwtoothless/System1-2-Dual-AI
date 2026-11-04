# System 1 & 2 Dual AI for Home Assistant

A high-performance, dual-model conversation agent for Home Assistant's Voice Assist pipelines. 

By splitting the voice pipeline into a **System 1 Decision Engine** (for zero-latency device control JSON generation) and a **System 2 Conversational Engine** (for natural TTS replies), this integration bypasses the extreme latency and hallucination problems of traditional single-LLM voice assistants.

## Features
- **Hybrid Routing:** Mix and match local inference (Ollama) and cloud inference (OpenRouter) on a per-model basis.
- **VRAM Optimized:** Keep heavy lifting in the cloud while routing conversational tasks to a local edge node, or vice versa.
- **Context Injection:** Automatically injects the triggering speaker's Area to resolve ambiguous commands (e.g., "turn on the lights").
- **Chat Fallback:** Gracefully falls back to answering general knowledge questions ("What time is it?") without attempting to parse device controls.

## Installation via HACS
1. Open Home Assistant and navigate to **HACS > Integrations**.
2. Click the three dots in the top right corner and select **Custom repositories**.
3. Add the URL to this repository and select **Integration** as the category.
4. Click **Download** and restart Home Assistant.

## Configuration
Go to **Settings > Devices & Services > Add Integration** and search for "System 1 & 2 Dual AI".
You will be prompted to select your inference providers (Ollama or OpenRouter) and specify the model endpoints and API keys.