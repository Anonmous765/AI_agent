"""Flask web wrapper around the existing Gemini situational awareness chat."""

from __future__ import annotations

import importlib.util
import threading
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request


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


# Import the Gemini module once at startup, then initialize the chat explicitly.
gemini_module = load_gemini_module()
chat = gemini_module.initialize_chat()

# Protect the shared chat object so two HTTP requests do not call send_message at the same time.
chat_lock = threading.Lock()


app = Flask(__name__)


@app.get("/")
def index():
    """Serve the main chat page."""
    return render_template("index.html")


@app.post("/chat")
def chat_route():
    """Accept a JSON message, send it to Gemini, and return the reply."""
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()

    if not message:
        return jsonify({"error": "Message is required."}), 400

    try:
        with chat_lock:
            response = chat.send_message(message)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500

    return jsonify({"reply": getattr(response, "text", "")})


if __name__ == "__main__":
    # Disable the reloader so the startup pipeline does not run twice in development.
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
