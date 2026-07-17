"""LLM provider for the LangChain / LangGraph agents.

Agents reason with Claude via `langchain-anthropic` when ANTHROPIC_API_KEY is set.
Without a key, `get_chat_model()` returns None and the agent graphs route to their
deterministic template node — so the platform still runs end-to-end offline.
"""
import os

DEFAULT_MODEL = os.environ.get("HC_CLAUDE_MODEL", "claude-sonnet-5")


def _langchain_anthropic_available() -> bool:
    try:
        import langchain_anthropic  # noqa: F401
        return True
    except Exception:
        return False


CLAUDE_AVAILABLE = bool(os.environ.get("ANTHROPIC_API_KEY")) and _langchain_anthropic_available()


def get_chat_model(max_tokens: int = 800):
    """Return a LangChain ChatAnthropic model, or None when offline."""
    if not CLAUDE_AVAILABLE:
        return None
    try:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=DEFAULT_MODEL, max_tokens=max_tokens)
    except Exception:
        return None


def invoke_text(model, system: str, prompt: str) -> str:
    """Run a single system+user turn through a LangChain chat model."""
    from langchain_core.messages import SystemMessage, HumanMessage

    resp = model.invoke([SystemMessage(content=system), HumanMessage(content=prompt)])
    content = resp.content
    if isinstance(content, list):  # some providers return content blocks
        content = "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        )
    return content
