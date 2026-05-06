"""Gemini chat factory and persistence helpers — no Flask dependency."""

from __future__ import annotations

import functools
import importlib.util
import queue
from pathlib import Path

from memory.chat_store import DEFAULT_SESSION_TITLE, add_message_pair

_HERE = Path(__file__).resolve().parent
_GEMINI_PATH = _HERE / "Gemini.py"

MODEL_NAME = "gemini-3-flash-preview"
MAX_HISTORY_MESSAGES = 6

_TOOL_LABELS: dict[str, str] = {
    "query_db": "Querying knowledge base",
    "fetch_noaa_alerts": "Fetching NOAA weather alerts",
    "query_gauges": "Querying flood gauge data",
    "query_crests": "Querying historical crest records",
    "web_search": "Searching the web",
}


def _load_gemini_module():
    spec = importlib.util.spec_from_file_location("disasterai_gemini", _GEMINI_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Gemini.py from {_GEMINI_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gemini_module = _load_gemini_module()


def derive_session_title(message: str, max_length: int = 60) -> str:
    """Generate a compact session title from the first user message."""
    collapsed = " ".join(message.split())
    if not collapsed:
        return DEFAULT_SESSION_TITLE
    if len(collapsed) <= max_length:
        return collapsed
    return f"{collapsed[: max_length - 1].rstrip()}..."


def _gemini_history(messages: list[dict]) -> list:
    """Convert recent persisted messages into Gemini chat history."""
    history = []
    for message in messages[-MAX_HISTORY_MESSAGES:]:
        role = "model" if message["role"] == "assistant" else "user"
        history.append(
            gemini_module.types.Content(
                role=role,
                parts=[gemini_module.types.Part(text=message["content"])],
            )
        )
    return history


def _default_tools() -> list:
    """Return the production data-retrieval tools."""
    return [
        gemini_module.query_db,
        gemini_module.fetch_noaa_alerts,
        gemini_module.query_gauges,
        gemini_module.query_crests,
        gemini_module.web_search,
    ]


def create_chat_with_history(
    messages: list[dict],
    *,
    system_instruction: str | None = None,
    tools: list | None = None,
):
    """Create a fresh Gemini chat seeded with previously stored turns."""
    config_kwargs = {
        "system_instruction": system_instruction or gemini_module.system_prompt,
    }
    if tools is None:
        tools = _default_tools()
    if tools:
        config_kwargs["tools"] = tools

    return gemini_module.client.chats.create(
        model=MODEL_NAME,
        config=gemini_module.types.GenerateContentConfig(**config_kwargs),
        history=_gemini_history(messages),
    )


def _save_exchange(
    session: dict,
    session_id: str,
    previous_messages: list[dict],
    message: str,
    reply: str,
) -> dict | None:
    """Persist a user/assistant exchange and update the title on first message."""
    generated_title = None
    if not previous_messages and session["title"] == DEFAULT_SESSION_TITLE:
        generated_title = derive_session_title(message)

    return add_message_pair(
        session_id,
        message,
        reply,
        title=generated_title,
    )


def _chat_response(
    reply: str,
    session_id: str,
    session: dict,
    previous_messages: list[dict],
    message: str,
) -> dict | None:
    """Persist a non-streaming exchange and return the response payload, or None on error."""
    updated_session = _save_exchange(session, session_id, previous_messages, message, reply)
    if updated_session is None:
        return None
    return {"reply": reply, "session_id": session_id, "session": updated_session}


def _make_tool_wrapper(fn, event_queue: queue.Queue):
    """Wrap a Gemini tool function to emit SSE events when it runs."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        label = _TOOL_LABELS.get(fn.__name__, fn.__name__)
        event_queue.put(("tool_call", {"name": fn.__name__, "label": label}))
        result = fn(*args, **kwargs)
        event_queue.put(("tool_done", {"name": fn.__name__}))
        return result
    return wrapper
