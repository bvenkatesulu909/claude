# Hermes agent on Telegram

A Telegram bot whose reasoning brain is a Nous Research **Hermes** model served
via **OpenRouter**. Each message runs an agent loop: reason → call tools →
observe → repeat → reply.

```
Telegram user
   │  message
   ▼
Telegram Bot API  (long polling)
   ▼
agent.py (this bot)
   ▼
┌─ agent loop ───────────────────────────┐
│  Hermes model ──act──▶ tools           │
│      ▲                   │ observe      │
│      └──── context ◀── memory ◀────────┘
└────────────────────────────────────────┘
   │ final reply
   ▼
Telegram user
```

## 1. Create the Telegram bot
1. In Telegram, message **@BotFather** → `/newbot` → pick a name and username.
2. Copy the token it gives you (looks like `123456:ABC…`).

## 2. Get an OpenRouter key
- Sign in at https://openrouter.ai → **Keys** → create a key.
- Add a little credit (Hermes 4 405B ≈ $1 / 1M tokens; the 70B is ~8× cheaper;
  `nousresearch/hermes-3-llama-3.1-405b:free` is free for testing).

## 3. Configure
```bash
cp .env.example .env      # then edit .env with your two tokens
```

## 4. Install and run
```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
python agent.py
```

Message your bot in Telegram. Try:
- "What's 2^10 minus 24?" (uses the calculator tool)
- "What time is it right now?" (uses the time tool)
- `/reset` clears that chat's memory.

## How it maps to the code (`agent.py`)
| Diagram piece      | In code                                             |
|--------------------|-----------------------------------------------------|
| Telegram transport | `python-telegram-bot` handlers + `run_polling()`    |
| Hermes model       | `client.chat.completions.create(...)` on OpenRouter |
| Tools              | `TOOLS_SPEC` (schemas) + `TOOL_IMPL` (functions)    |
| Agent loop         | `run_agent()` — the `for _ in range(MAX_TOOL_TURNS)`|
| Memory             | `HISTORY[chat_id]` list of messages                 |

## Adding a tool
1. Write a Python function.
2. Add its JSON schema to `TOOLS_SPEC`.
3. Register it in `TOOL_IMPL`.
The model discovers it automatically on the next turn.

## Production notes
- **Memory** is in-process (lost on restart). Swap `HISTORY` for Redis/SQLite,
  and trim old turns so you stay under the 128K context window.
- **Webhooks vs polling**: polling is simplest and used here. For scale, host
  behind HTTPS and use `app.run_webhook(...)` instead.
- **Tool calling**: uses the standard OpenAI-style `tools` API, which OpenRouter
  passes through to Hermes. If a specific endpoint rejects native tools, either
  pin a provider that supports them or fall back to Hermes' prompt-based
  `<tool_call>` format.
