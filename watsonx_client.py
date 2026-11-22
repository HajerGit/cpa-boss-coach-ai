"""
watsonx_client.py — Task delivery for CPA Boss Coach.

Default mode: serves tasks from task_bank.json (24 hand-written FAR tasks, written with IBM Bob).
Optional AI mode: if WATSONX_APIKEY / WATSONX_PROJECT_ID / WATSONX_URL are configured,
  IBM Granite on watsonx.ai generates additional tasks on the fly.
  Falls back to task_bank.json automatically on any error.
"""

from __future__ import annotations

import json
import logging
import os
import random
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Credential loading
# ---------------------------------------------------------------------------

def _load_credentials() -> tuple[str, str, str]:
    """Return (api_key, project_id, url) from environment or Streamlit secrets."""
    # Try .env / environment variables first (works locally after `python-dotenv` loads them)
    api_key = os.getenv("WATSONX_APIKEY", "")
    project_id = os.getenv("WATSONX_PROJECT_ID", "")
    url = os.getenv("WATSONX_URL", "")

    # If running on Streamlit Cloud, secrets are injected as env vars by default,
    # but we also try the streamlit.secrets dict for explicit support.
    if not api_key:
        try:
            import streamlit as st  # type: ignore
            api_key = st.secrets.get("WATSONX_APIKEY", "")
            project_id = st.secrets.get("WATSONX_PROJECT_ID", "")
            url = st.secrets.get("WATSONX_URL", "")
        except Exception:
            pass

    return api_key, project_id, url


def _credentials_available() -> bool:
    api_key, project_id, url = _load_credentials()
    return bool(api_key and project_id and url)


# ---------------------------------------------------------------------------
# Task bank (primary source — task_bank.json, written with IBM Bob)
# ---------------------------------------------------------------------------

_TASK_BANK: list[dict] | None = None


def _load_task_bank() -> list[dict]:
    global _TASK_BANK
    if _TASK_BANK is None:
        bank_path = Path(__file__).parent / "task_bank.json"
        with bank_path.open("r", encoding="utf-8") as fh:
            _TASK_BANK = json.load(fh)
    return _TASK_BANK


def get_bank_task(topic: str, exclude_ids: list[str] | None = None) -> dict:
    """Return a random task-bank task for the given topic, avoiding already-used IDs."""
    tasks = _load_task_bank()
    topic_tasks = [t for t in tasks if t["topic"] == topic]
    if not topic_tasks:
        topic_tasks = tasks  # safety fallback if topic not found

    exclude_ids = exclude_ids or []
    available = [t for t in topic_tasks if t["id"] not in exclude_ids]
    if not available:
        # All topic tasks have been used — reset so the session can continue
        available = topic_tasks

    return dict(random.choice(available))


# ---------------------------------------------------------------------------
# JSON validation
# ---------------------------------------------------------------------------

REQUIRED_TASK_KEYS = {"id", "topic", "scenario", "question", "options", "correct", "explanation"}
REQUIRED_OPTION_KEYS = {"A", "B", "C", "D"}
REQUIRED_EXPLANATION_BASE_KEYS = {"correct_reason", "tip"}


def _validate_task(data: Any) -> bool:
    """Return True if data matches the expected task schema.

    why_not_X is only required for the three letters that are NOT the correct answer,
    since the model may (correctly) omit it for the answer it chose as correct.
    """
    if not isinstance(data, dict):
        return False
    if not REQUIRED_TASK_KEYS.issubset(data.keys()):
        return False
    if not isinstance(data.get("options"), dict):
        return False
    if not REQUIRED_OPTION_KEYS.issubset(data["options"].keys()):
        return False
    correct = data.get("correct")
    if correct not in ("A", "B", "C", "D"):
        return False
    if not isinstance(data.get("explanation"), dict):
        return False
    exp = data["explanation"]
    # Base keys always required
    if not REQUIRED_EXPLANATION_BASE_KEYS.issubset(exp.keys()):
        return False
    # why_not_X required only for the three wrong options
    for letter in ("A", "B", "C", "D"):
        if letter != correct and f"why_not_{letter}" not in exp:
            return False
    return True


# ---------------------------------------------------------------------------
# Option shuffling
# ---------------------------------------------------------------------------

def shuffle_options(task: dict) -> dict:
    """Return a copy of *task* with options shuffled to a random letter assignment.

    Remaps:
      - task["options"]   — the displayed text for each letter
      - task["correct"]   — the new letter for the originally-correct answer
      - explanation["why_not_X"] keys — follow the shuffled letters so feedback
        always references the letter the user sees on screen
    """
    import copy

    task = copy.deepcopy(task)
    old_letters = ["A", "B", "C", "D"]
    new_letters = old_letters[:]
    random.shuffle(new_letters)

    # Build mapping: old_letter -> new_letter
    old_to_new = {old: new for old, new in zip(old_letters, new_letters)}

    # Remap options dict
    old_options = task["options"]
    task["options"] = {old_to_new[k]: v for k, v in old_options.items()}

    # Remap correct answer
    task["correct"] = old_to_new[task["correct"]]

    # Remap why_not_X keys in explanation
    exp = task["explanation"]
    new_exp = {k: v for k, v in exp.items() if not k.startswith("why_not_")}
    for old_letter in old_letters:
        old_key = f"why_not_{old_letter}"
        new_key = f"why_not_{old_to_new[old_letter]}"
        if old_key in exp:
            new_exp[new_key] = exp[old_key]
    task["explanation"] = new_exp

    return task


# ---------------------------------------------------------------------------
# watsonx.ai call
# ---------------------------------------------------------------------------

GRANITE_MODEL_ID = "ibm/granite-3-3-8b-instruct"


def _call_watsonx(prompt: str) -> str:
    """Call IBM Granite and return the raw text response."""
    from ibm_watsonx_ai import APIClient, Credentials  # type: ignore
    from ibm_watsonx_ai.foundation_models import ModelInference  # type: ignore

    api_key, project_id, url = _load_credentials()

    credentials = Credentials(url=url, api_key=api_key)
    client = APIClient(credentials)

    model = ModelInference(
        model_id=GRANITE_MODEL_ID,
        api_client=client,
        project_id=project_id,
        params={
            "max_new_tokens": 1200,
            "temperature": 0.3,
            "stop_sequences": [],
        },
    )

    response = model.generate_text(prompt=prompt)
    return response  # type: ignore[return-value]


def _extract_json(raw: str) -> dict | None:
    """Try to extract a JSON object from a raw string (handles markdown fences)."""
    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # remove first and last fence lines
        inner = "\n".join(lines[1:] if lines[0].startswith("```") else lines)
        inner = inner.rsplit("```", 1)[0].strip()
        text = inner

    # Find the first '{' and last '}'
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def generate_task(
    topic: str,
    session_minutes: int,
    exclude_ids: list[str] | None = None,
) -> tuple[dict, bool]:
    """
    Generate a CPA task.

    Returns:
        (task_dict, is_ai_generated)
        is_ai_generated is False when falling back to the built-in bank.
    """
    from prompts import TASK_GENERATION_PROMPT  # local import to avoid circular refs

    if not _credentials_available():
        logger.info("watsonx credentials not configured — serving from task bank.")
        return shuffle_options(get_bank_task(topic, exclude_ids)), False

    prompt = TASK_GENERATION_PROMPT.format(topic=topic, session_minutes=session_minutes)

    for attempt in range(2):  # try once, retry once on invalid JSON
        try:
            raw = _call_watsonx(prompt)
            data = _extract_json(raw)
            if data and _validate_task(data):
                data["id"] = f"generated_{random.randint(1000, 9999)}"
                data["topic"] = topic  # ensure topic matches
                return shuffle_options(data), True
            else:
                logger.warning("Attempt %d: invalid JSON from watsonx. Retrying...", attempt + 1)
        except Exception as exc:
            logger.warning("Attempt %d: watsonx call failed: %s", attempt + 1, exc)

    logger.info("watsonx call failed — serving from task bank.")
    return shuffle_options(get_bank_task(topic, exclude_ids)), False
