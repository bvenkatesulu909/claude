# OpenAI Agents SDK on OpenRouter (`tencent/hy3`)

A minimal, working end-to-end setup of the **OpenAI Agents SDK** driven by the
**`tencent/hy3`** model via OpenRouter — including a real agentic tool-calling loop.

## Files
- `agent_hy3.py` — the agent (two tools: `get_weather`, `add`)
- `.env` — your OpenRouter key + model (git-ignored)
- `.env.example` — template
- `requirements.txt`

## Setup
```bash
pip install -r requirements.txt
cp .env.example .env   # then paste your OpenRouter key
```

## Run
```bash
python agent_hy3.py
python agent_hy3.py "your own question"
```

## The two OpenRouter-specific gotchas
1. **Chat Completions, not Responses.** The SDK defaults to OpenAI's Responses
   API; OpenRouter only speaks Chat Completions. We wrap the model in
   `OpenAIChatCompletionsModel(model=..., openai_client=client)` where `client`
   is an `AsyncOpenAI` pointed at `https://openrouter.ai/api/v1`.
2. **Tracing off.** The SDK's tracing exporter uploads to platform.openai.com
   and needs `OPENAI_API_KEY`. With an OpenRouter-only setup, call
   `set_tracing_disabled(True)` to silence it.

## Model notes
- `tencent/hy3` — paid, ~$0.20/M tokens, 262K context, tool calling + structured output.
- `tencent/hy3:free` — free variant, same capabilities, may rate-limit. Switch by
  setting `OPENROUTER_MODEL=tencent/hy3:free` in `.env`.
