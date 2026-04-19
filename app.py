"""Flask web wrapper around the existing Gemini situational awareness chat."""

from __future__ import annotations

import importlib.util
import threading
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from database.chat_store import (
    DEFAULT_SESSION_TITLE,
    add_message_pair,
    create_session,
    delete_session,
    get_session,
    init_db,
    list_messages,
    list_sessions,
    rename_session,
)


load_dotenv()


# Build absolute paths from the project root so the app works reliably when started locally.
PROJECT_ROOT = Path(__file__).resolve().parent
GEMINI_PATH = PROJECT_ROOT / "LLM Reasoning" / "Gemini.py"


def load_gemini_module():
    """Load the existing Gemini.py file as a module."""
    spec = importlib.util.spec_from_file_location("disasterai_gemini", GEMINI_PATH)

    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Gemini.py from {GEMINI_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Import the Gemini module once at startup, then run its startup population flow.
gemini_module = load_gemini_module()
gemini_module.initialize_chat()

# Persist chat sessions before the first request arrives.
init_db()

# Protect the Gemini client and backing tools from concurrent request races.
chat_lock = threading.Lock()

app = Flask(__name__)


def derive_session_title(message: str, max_length: int = 60) -> str:
    """Generate a compact session title from the first user message."""
    collapsed = " ".join(message.split())
    if not collapsed:
        return DEFAULT_SESSION_TITLE
    if len(collapsed) <= max_length:
        return collapsed
    return f"{collapsed[: max_length - 1].rstrip()}..."


def create_chat_with_history(messages: list[dict]):
    """Create a fresh Gemini chat seeded with previously stored turns."""
    history = []
    for message in messages:
        role = "model" if message["role"] == "assistant" else "user"
        history.append(
            gemini_module.types.Content(
                role=role,
                parts=[gemini_module.types.Part(text=message["content"])],
            )
        )

    return gemini_module.client.chats.create(
        model="gemini-3-flash-preview",
        config=gemini_module.types.GenerateContentConfig(
            system_instruction=gemini_module.system_prompt,
            tools=[gemini_module.query_db, gemini_module.fetch_noaa_alerts],
        ),
        history=history,
    )


@app.get("/")
def index():
    """Serve the main chat page."""
    return render_template("index.html")


@app.get("/sessions")
def list_sessions_route():
    """Return all saved chat sessions."""
    return jsonify({"sessions": list_sessions()})


@app.post("/sessions")
def create_session_route():
    """Create a new chat session."""
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title", "")).strip() or DEFAULT_SESSION_TITLE
    session = create_session(title=title)
    return jsonify({"id": session["id"], "session": session}), 201


@app.get("/sessions/<session_id>")
def get_session_route(session_id: str):
    """Return a session and all persisted messages."""
    session = get_session(session_id)
    if session is None:
        return jsonify({"error": "Session not found."}), 404

    return jsonify({"session": session, "messages": list_messages(session_id)})


@app.patch("/sessions/<session_id>")
def rename_session_route(session_id: str):
    """Rename a persisted chat session."""
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title", "")).strip()
    if not title:
        return jsonify({"error": "Title is required."}), 400

    try:
        session = rename_session(session_id, title)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if session is None:
        return jsonify({"error": "Session not found."}), 404

    return jsonify({"session": session})


@app.delete("/sessions/<session_id>")
def delete_session_route(session_id: str):
    """Delete a session and its message history."""
    if not delete_session(session_id):
        return jsonify({"error": "Session not found."}), 404

    return jsonify({"deleted": True, "id": session_id})


@app.post("/chat")
def chat_route():
    """Accept a JSON message, persist it, and return Gemini's reply."""
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    session_id = str(payload.get("session_id", "")).strip()

    if not message:
        return jsonify({"error": "Message is required."}), 400

    session = get_session(session_id) if session_id else None
    if session_id and session is None:
        return jsonify({"error": "Session not found."}), 404

    if session is None:
        session = create_session()
        session_id = session["id"]

    previous_messages = list_messages(session_id)

    try:
        with chat_lock:
            chat = create_chat_with_history(previous_messages)
            response = chat.send_message(message)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500

    reply = getattr(response, "text", "")
    generated_title = None
    if not previous_messages and session["title"] == DEFAULT_SESSION_TITLE:
        generated_title = derive_session_title(message)

    updated_session = add_message_pair(
        session_id,
        message,
        reply,
        title=generated_title,
    )
    if updated_session is None:
        return jsonify({"error": "Session not found."}), 404

    return jsonify(
        {
            "reply": reply,
            "session_id": session_id,
            "session": updated_session,
        }
    )


if __name__ == "__main__":
    # Disable the reloader so the startup pipeline does not run twice in development.
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
