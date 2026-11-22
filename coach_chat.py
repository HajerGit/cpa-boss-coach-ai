"""
coach_chat.py — "Ask the Coach" chatbot for CPA Boss Coach.

After each task, the student can ask follow-up questions ("Why is C wrong?",
"Explain it more simply", "Give me a similar example"). Every question is sent
to Google Gemini together with the current task (scenario, options, correct
answer, and the Coach's explanations), so answers stay grounded in that task.

Setup: put GEMINI_API_KEY in Streamlit secrets or in a local .env file.
Optional: GEMINI_MODEL to choose a specific model.
"""

from __future__ import annotations

import os

# Tried in order if GEMINI_MODEL is not set. Google renames models often,
# so if none of these work we ask the API which Flash models exist.
DEFAULT_MODELS = ["gemini-flash-latest", "gemini-flash-lite-latest"]

MAX_TURNS_PER_TASK = 8  # student questions per task, protects the free quota

SYSTEM_PROMPT = """You are "the Coach" in CPA Boss Coach, a study app for the CPA exam's FAR section.
A student just answered a practice task. The full task and the official explanations are below.

How to answer:
- Base your answer on the task and the official explanations. Do not contradict the official correct answer.
- Cite the relevant ASC standard when it helps (for example ASC 606, ASC 842, ASC 330, ASC 835).
- Be clear and friendly, like a senior accountant helping a new staff member. Use plain words.
- Keep answers short: usually under 150 words. Use a short journal entry or a simple calculation when it helps.
- If the student asks for a similar example, make up a new short example on the same rule and show the answer.
- Only help with accounting and CPA exam topics. If asked about something else, politely steer back to the task.
- If you are not sure about something, say so and tell the student to check the ASC standard.
- Never make up ASC paragraph numbers.

THE TASK
{task_block}
"""


def get_api_key() -> str:
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        try:
            import streamlit as st  # type: ignore
            key = st.secrets.get("GEMINI_API_KEY", "")
        except Exception:
            pass
    return key


def is_available() -> bool:
    return bool(get_api_key())


def _get_setting(name: str) -> str:
    val = os.getenv(name, "")
    if not val:
        try:
            import streamlit as st  # type: ignore
            val = st.secrets.get(name, "")
        except Exception:
            pass
    return val


def build_task_block(task: dict, user_choice: str | None) -> str:
    """Turn the current task into plain text the model can read."""
    opts = task["options"]
    exp = task.get("explanation", {})
    lines = [
        f"Topic: {task.get('topic', '')}",
        "Scenario:",
        task["scenario"],
        "",
        f"Question: {task['question']}",
    ]
    for k in sorted(opts):
        lines.append(f"{k}. {opts[k]}")
    lines.append("")
    lines.append(f"Correct answer: {task['correct']}")
    if user_choice:
        result = "correct" if user_choice == task["correct"] else "wrong"
        lines.append(f"The student chose: {user_choice} ({result})")
    lines.append("")
    lines.append(f"Why {task['correct']} is correct: {exp.get('correct_reason', '')}")
    for k in sorted(opts):
        why = exp.get(f"why_not_{k}")
        if k != task["correct"] and why:
            lines.append(f"Why not {k}: {why}")
    if exp.get("tip"):
        lines.append(f"Exam tip: {exp['tip']}")
    return "\n".join(lines)


def build_contents(history: list[dict]) -> list[dict]:
    """Convert chat history [{'role': 'user'|'assistant', 'content': str}] to Gemini format."""
    contents = []
    for m in history:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    return contents


_client = None
_client_key: str | None = None
_working_model: str | None = None


def _client_and_models():
    global _client, _client_key
    from google import genai  # imported here so the app still starts without the package

    key = get_api_key()
    if _client is None or key != _client_key:  # rebuild if the key in secrets was changed
        _client = genai.Client(api_key=key)
        _client_key = key
    chosen = _get_setting("GEMINI_MODEL")
    models = [chosen] if chosen else []
    if _working_model:
        models.insert(0, _working_model)
    models += [m for m in DEFAULT_MODELS if m not in models]
    return _client, models


def _discover_flash_models(client) -> list[str]:
    """Ask the API which Flash text models this key can use."""
    found = []
    try:
        for m in client.models.list():
            name = (getattr(m, "name", "") or "").replace("models/", "")
            actions = getattr(m, "supported_actions", None) or []
            if "flash" in name and "image" not in name and "tts" not in name and "audio" not in name \
                    and (not actions or "generateContent" in actions):
                found.append(name)
    except Exception:
        pass
    # Prefer "latest" aliases, then newest-looking names
    return sorted(found, key=lambda n: ("latest" not in n, "lite" in n, n), reverse=False)


def ask_coach(task: dict, user_choice: str | None, history: list[dict]) -> str:
    """Send the conversation to Gemini and return the Coach's reply text.

    Raises RuntimeError with a student-friendly message if something goes wrong.
    """
    global _working_model
    if not is_available():
        raise RuntimeError("Ask the Coach is not set up yet (missing GEMINI_API_KEY).")

    from google.genai import types

    client, models = _client_and_models()
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT.format(task_block=build_task_block(task, user_choice)),
        temperature=0.3,
        # Newer Gemini models "think" before answering, and that thinking counts toward
        # this limit. A low limit cuts answers off mid-sentence, so keep it generous;
        # the prompt itself keeps answers short.
        max_output_tokens=4096,
    )
    contents = build_contents(history)

    last_err: Exception | None = None
    tried: set[str] = set()
    for attempt in range(2):
        for model in models:
            if model in tried:
                continue
            tried.add(model)
            try:
                resp = client.models.generate_content(model=model, contents=contents, config=config)
                text = (getattr(resp, "text", None) or "").strip()
                if text:
                    _working_model = model
                    return text
            except Exception as e:  # model missing, quota, network...
                last_err = e
                msg = str(e).lower()
                if "api key" in msg or "permission" in msg or "unauthenticated" in msg:
                    raise RuntimeError("The Gemini API key was rejected. Check GEMINI_API_KEY in your secrets.") from e
                if "429" in msg or "quota" in msg or "resource_exhausted" in msg:
                    raise RuntimeError("The Coach is getting too many questions right now. Wait a minute and try again.") from e
        if attempt == 0:
            models = _discover_flash_models(client)
    raise RuntimeError("The Coach couldn't answer right now. Please try again in a moment.") from last_err
