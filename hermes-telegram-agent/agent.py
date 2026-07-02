"""Hermes agent on Telegram.

A Telegram bot whose "brain" is a Nous Research Hermes model served via
OpenRouter. Each incoming message runs an agent loop: the model reasons,
optionally calls tools, observes the results, and repeats until it produces
a final answer, which is sent back to the user as a reply.

Run:  python agent.py
Env:  TELEGRAM_BOT_TOKEN, OPENROUTER_API_KEY  (see .env.example)
"""

import os
import json
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update, constants
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s  %(name)s  %(levelname)s  %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("hermes")

# --- Hermes model via OpenRouter --------------------------------------------
# Swap to nousresearch/hermes-4-70b for a cheaper run, or
# nousresearch/hermes-3-llama-3.1-405b:free for free testing.
MODEL = os.getenv("HERMES_MODEL", "nousresearch/hermes-4-405b")
MAX_TOOL_TURNS = 6  # safety cap on the reason -> act -> observe loop

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
    default_headers={
        # Optional but recommended by OpenRouter for attribution.
        "HTTP-Referer": "https://t.me",
        "X-Title": "Hermes Telegram Agent",
    },
)

SYSTEM_PROMPT = (
    "You are Hermes, a helpful assistant operating inside a Telegram chat. "
    "Keep replies concise and use plain text (Telegram markdown is fine). "
    "When a tool can give you a precise answer, call it instead of guessing."
)

# --- Tools ------------------------------------------------------------------
# Each tool = a JSON schema (sent to the model) + a Python function that runs it.

def tool_get_current_time(timezone_name: str = "UTC") -> str:
    now = datetime.now(timezone.utc)
    return f"The current UTC time is {now.strftime('%Y-%m-%d %H:%M:%S')} UTC."


def tool_calculator(expression: str) -> str:
    # Tiny safe arithmetic evaluator (no builtins, no names).
    allowed = set("0123456789+-*/(). %")
    if not set(expression) <= allowed:
        return "Error: only basic arithmetic is allowed."
    try:
        return f"{expression} = {eval(expression, {'__builtins__': {}}, {})}"
    except Exception as exc:  # noqa: BLE001
        return f"Error evaluating expression: {exc}"


TOOLS_SPEC = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current UTC date and time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone_name": {
                        "type": "string",
                        "description": "IANA timezone name, defaults to UTC.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a basic arithmetic expression.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "e.g. '(12 * 7) + 3'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
]

TOOL_IMPL = {
    "get_current_time": tool_get_current_time,
    "calculator": tool_calculator,
}

# --- Per-chat conversation memory -------------------------------------------
# In-memory only; swap for Redis/SQLite to persist across restarts.
HISTORY: dict[int, list[dict]] = {}


def get_history(chat_id: int) -> list[dict]:
    if chat_id not in HISTORY:
        HISTORY[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    return HISTORY[chat_id]


def run_agent(chat_id: int, user_text: str) -> str:
    """The agent loop: reason -> (maybe) call tools -> observe -> repeat."""
    messages = get_history(chat_id)
    messages.append({"role": "user", "content": user_text})

    for _ in range(MAX_TOOL_TURNS):
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS_SPEC,
            tool_choice="auto",
            temperature=0.7,
        )
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            # No tool needed -> this is the final answer.
            return msg.content or "(no response)"

        # Execute each requested tool and feed results back as observations.
        for call in msg.tool_calls:
            fn = TOOL_IMPL.get(call.function.name)
            try:
                args = json.loads(call.function.arguments or "{}")
                result = fn(**args) if fn else f"Unknown tool: {call.function.name}"
            except Exception as exc:  # noqa: BLE001
                result = f"Tool error: {exc}"
            log.info("tool %s(%s) -> %s", call.function.name, args, result)
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": str(result),
            })

    return "Sorry, I hit the tool-call limit before finishing. Try rephrasing."


# --- Telegram handlers ------------------------------------------------------
async def cmd_start(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hi, I'm a Hermes agent. Ask me anything — I can reason and use tools."
    )


async def cmd_reset(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    HISTORY.pop(update.effective_chat.id, None)
    await update.message.reply_text("Conversation memory cleared.")


async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await ctx.bot.send_chat_action(chat_id, constants.ChatAction.TYPING)
    try:
        # run_agent is blocking (sync OpenAI calls) -> run off the event loop.
        import asyncio
        answer = await asyncio.to_thread(run_agent, chat_id, update.message.text)
    except Exception as exc:  # noqa: BLE001
        log.exception("agent failed")
        answer = f"Something went wrong: {exc}"
    await update.message.reply_text(answer)


def main() -> None:
    app = Application.builder().token(os.environ["TELEGRAM_BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    log.info("Hermes agent starting (model=%s)…", MODEL)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
