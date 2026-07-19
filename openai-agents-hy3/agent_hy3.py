"""
OpenAI Agents SDK, end-to-end, running on OpenRouter's `tencent/hy3` model.

Why the extra wiring vs. a vanilla Agents SDK example:
  - The SDK defaults to OpenAI's *Responses* API. OpenRouter only speaks the
    *Chat Completions* API, so we wrap the model in OpenAIChatCompletionsModel.
  - The SDK's tracing exporter uploads to platform.openai.com and needs an
    OPENAI_API_KEY. We have none (OpenRouter only), so tracing is disabled.

Run:  python agent_hy3.py
      python agent_hy3.py "your own question here"
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from openai import AsyncOpenAI

from agents import (
    Agent,
    OpenAIChatCompletionsModel,
    Runner,
    function_tool,
    set_tracing_disabled,
)

load_dotenv()

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
MODEL = os.getenv("OPENROUTER_MODEL", "tencent/hy3")

# No OpenAI key in this project -> turn the tracing uploader off so it doesn't
# warn/fail on every run.
set_tracing_disabled(True)

# One shared OpenAI-compatible client pointed at OpenRouter.
client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

model = OpenAIChatCompletionsModel(model=MODEL, openai_client=client)


# --- A tool the model can call. The whole point of the Agents SDK is the
#     agentic loop: model -> tool call -> tool result -> model -> final answer. ---
@function_tool
def get_weather(city: str) -> str:
    """Return the current weather for a city (demo stub, no real API)."""
    return f"The weather in {city} is 22 C and sunny."


@function_tool
def add(a: float, b: float) -> str:
    """Add two numbers and return the sum."""
    return str(a + b)


agent = Agent(
    name="Hy3 Assistant",
    instructions=(
        "You are a concise, helpful assistant. "
        "Use the provided tools when they are relevant instead of guessing."
    ),
    model=model,
    tools=[get_weather, add],
)


async def main() -> None:
    prompt = (
        " ".join(sys.argv[1:])
        or "What's the weather in Tokyo, and what is 21 + 21? Answer in one sentence."
    )
    result = await Runner.run(agent, prompt)
    print("\n=== Final output ===")
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
