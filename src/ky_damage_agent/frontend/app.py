"""Flask web wrapper around the existing Gemini situational awareness chat."""

from __future__ import annotations

import json
import queue
import re
import threading
import time

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request

from ky_damage_agent.paths import ENV_FILE
from ky_damage_agent.memory.chat_store import (
    DEFAULT_SESSION_TITLE,
    create_session,
    delete_session,
    get_session,
    init_db,
    list_messages,
    list_sessions,
    rename_session,
)

load_dotenv(dotenv_path=ENV_FILE)

from ky_damage_agent.llm_reasoning.gemini_chat import (
    _chat_response,
    _make_tool_wrapper,
    _save_exchange,
    create_chat_with_history,
    gemini_module,
)

# Run the startup pipeline (RSS population + Gemini session warm-up).
gemini_module.initialize_chat()

# Persist chat sessions before the first request arrives.
init_db()

# Protect the Gemini client and backing tools from concurrent request races.
chat_lock = threading.Lock()

app = Flask(__name__)


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

    reply = getattr(response, "text", "") or ""
    result = _chat_response(reply, session_id, session, previous_messages, message)
    if result is None:
        return jsonify({"error": "Session not found."}), 404
    return jsonify(result)


@app.post("/chat/stream")
def chat_stream_route():
    """SSE endpoint: emits tool-call events then streams the reply word-by-word."""
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

    eq: queue.Queue = queue.Queue()
    result: dict = {}

    def _run():
        try:
            tools = [
                _make_tool_wrapper(gemini_module.query_db, eq),
                _make_tool_wrapper(gemini_module.fetch_noaa_alerts, eq),
                _make_tool_wrapper(gemini_module.query_gauges, eq),
                _make_tool_wrapper(gemini_module.query_crests, eq),
                _make_tool_wrapper(gemini_module.web_search, eq),
            ]
            with chat_lock:
                chat = create_chat_with_history(
                    previous_messages,
                    tools=tools,
                )
                response = chat.send_message(message)
                result["reply"] = getattr(response, "text", "") or ""
        except Exception as exc:  # noqa: BLE001
            result["error"] = str(exc)
        finally:
            eq.put(("chat_done", {}))

    threading.Thread(target=_run, daemon=True).start()

    def _generate():
        # Relay tool-call events until Gemini finishes.
        while True:
            try:
                event_type, data = eq.get(timeout=120)
            except queue.Empty:
                yield f"event: error\ndata: {json.dumps({'error': 'Request timed out.'})}\n\n"
                return
            if event_type == "chat_done":
                break
            yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

        if "error" in result:
            yield f"event: error\ndata: {json.dumps({'error': result['error']})}\n\n"
            return

        reply = result.get("reply", "")
        updated_session = _save_exchange(session, session_id, previous_messages, message, reply)
        if updated_session is None:
            yield f"event: error\ndata: {json.dumps({'error': 'Session not found.'})}\n\n"
            return

        # Stream text token by token (words + whitespace preserved).
        for token in re.findall(r"\S+|\s+", reply):
            yield f"event: text\ndata: {json.dumps({'chunk': token})}\n\n"
            if not token.isspace():
                time.sleep(0.03)

        yield f"event: done\ndata: {json.dumps({'session_id': session_id, 'session': updated_session})}\n\n"

    return Response(
        _generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def main() -> None:
    """Run the Flask development server."""
    # Disable the reloader so the startup pipeline does not run twice in development.
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
