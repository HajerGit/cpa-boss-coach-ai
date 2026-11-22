"""
app.py — CPA Boss Coach: FAR exam study assistant.

Flow:
  1. User picks topic + session length → session starts.
  2. 'Boss' presents a flawed accounting task (from task_bank.json, written with IBM Bob).
  3. User picks a multiple-choice answer.
  4. 'Coach' gives full 'Why not the others?' feedback.
  5. Repeat until question budget is exhausted → summary + study plan.

Task source: practice bank written with IBM Bob (default).
             IBM watsonx.ai / Granite is used only when credentials are configured.
"""

from __future__ import annotations

import time
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv

# Load .env for local development (no-op if file doesn't exist)
load_dotenv()

# ---------------------------------------------------------------------------
# Page config — must be the first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="CPA Boss Coach",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TOPICS: dict[str, str] = {
    "revenue_recognition": "Revenue Recognition (ASC 606)",
    "leases": "Leases (ASC 842)",
    "inventory": "Inventory (ASC 330)",
    "bonds": "Bonds & Debt (ASC 835)",
}

SESSION_LENGTHS: dict[int, int] = {
    5: 3,   # ~3 questions in 5 minutes
    10: 6,
    15: 9,
}

# Questions per session length
QUESTIONS_PER_SESSION: dict[int, int] = SESSION_LENGTHS

# ---------------------------------------------------------------------------
# Minimal CSS — readable, accessible, no color-only information
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    /* ---- overall layout ---- */
    .main .block-container { max-width: 760px; padding-top: 2rem; }

    /*
     * Dark-mode contrast fix
     * All custom boxes keep a light background regardless of the OS/browser
     * colour scheme. Without an explicit text colour the browser may inherit
     * Streamlit's dark-theme foreground (near-white), making text invisible.
     * We pin every box — and all its descendants — to #1a1a1a so the
     * contrast ratio never drops below 15:1 against the lightest background
     * used here (#f0f4ff), well above the WCAG AA threshold of 4.5:1.
     */

    /* shared dark-text rule applied to every custom box */
    .boss-banner,
    .coach-banner,
    .scenario-box,
    .feedback-correct,
    .feedback-incorrect {
        color: #1a1a1a !important;
    }

    /* cascade to all inline/block children so nested tags inherit the value */
    .boss-banner *,
    .coach-banner *,
    .scenario-box *,
    .feedback-correct *,
    .feedback-incorrect * {
        color: #1a1a1a !important;
    }

    /* ---- persona banners ---- */
    .boss-banner {
        background: #f0f4ff;
        border-left: 4px solid #3b5bdb;
        padding: 1rem 1.25rem;
        border-radius: 4px;
        margin-bottom: 1rem;
    }
    .coach-banner {
        background: #f0fff4;
        border-left: 4px solid #2f9e44;
        padding: 1rem 1.25rem;
        border-radius: 4px;
        margin-bottom: 1rem;
    }

    /* ---- scenario pre-formatted text ---- */
    .scenario-box {
        background: #f7f8fa;
        border: 1px solid #e5e7eb;
        padding: 1rem 1.25rem;
        border-radius: 4px;
        font-family: "Courier New", monospace;
        font-size: 0.88rem;
        white-space: pre-wrap;
        margin-bottom: 1rem;
    }

    /* ---- feedback boxes ---- */
    .feedback-correct {
        background: #ebfbee;
        border: 1px solid #69db7c;
        padding: 1rem 1.25rem;
        border-radius: 4px;
        margin-top: 1rem;
    }
    .feedback-incorrect {
        background: #fff5f5;
        border: 1px solid #ff8787;
        padding: 1rem 1.25rem;
        border-radius: 4px;
        margin-top: 1rem;
    }

    /* ---- summary table ---- */
    .summary-table { width: 100%; border-collapse: collapse; margin-top: 1rem; background: #ffffff; }
    .summary-table th, .summary-table td {
        text-align: left; padding: 0.5rem 0.75rem;
        border-bottom: 1px solid #e5e7eb;
        color: #1a1a1a !important;   /* dark-mode fix: pin text colour */
    }
    .summary-table th { background: #f7f8fa; font-weight: 600; }

    /* ---- progress bar label ---- */
    .progress-label { font-size: 0.82rem; margin-top: 0.25rem; opacity: 0.85; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------

def _init_state() -> None:
    defaults: dict = {
        "screen": "setup",          # setup | question | feedback | summary
        "topic": None,
        "session_minutes": 5,
        "question_limit": 3,
        "questions_done": 0,
        "score": 0,
        # Each missed entry: {"topic_display": str, "tip": str}
        "missed_items": [],
        "current_task": None,
        "user_choice": None,
        "is_ai_task": False,
        # Per-topic used IDs to prevent repeats within a session
        "used_task_ids_by_topic": {},
        "session_start": None,
        "feedback_text": None,
        # "Ask the Coach" chat for the current task: [{"role", "content"}]
        "chat_history": [],
        "chat_error": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


_init_state()

# ---------------------------------------------------------------------------
# Lazy import of watsonx_client (keeps startup fast if keys missing)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def _get_watsonx_module():
    import watsonx_client  # noqa: PLC0415
    return watsonx_client


# ---------------------------------------------------------------------------
# Screen: SETUP
# ---------------------------------------------------------------------------

def screen_setup() -> None:
    st.title("📊 CPA Boss Coach")
    st.markdown(
        "**Your AI study partner for the CPA FAR exam.** "
        "The *Boss* gives you a realistic work task with a hidden error. "
        "You find it — the *Coach* explains why."
    )
    st.divider()

    st.subheader("1. Choose a topic")
    topic_key = st.radio(
        label="Select a FAR topic:",
        options=list(TOPICS.keys()),
        format_func=lambda k: TOPICS[k],
        key="topic_select",
        help="Pick the accounting area you want to practice.",
    )

    st.subheader("2. Choose a session length")
    minutes = st.radio(
        label="How long do you have?",
        options=[5, 10, 15],
        format_func=lambda m: f"{m} minutes (~{SESSION_LENGTHS[m]} questions)",
        key="minutes_select",
        horizontal=True,
    )

    st.divider()
    if st.button("▶ Start Session", type="primary", use_container_width=True):
        st.session_state.topic = topic_key
        st.session_state.session_minutes = minutes
        st.session_state.question_limit = SESSION_LENGTHS[minutes]
        st.session_state.screen = "question"
        st.session_state.session_start = time.time()
        st.rerun()

    # Small disclaimer, first screen only
    st.markdown(
        "<p style='font-size:0.72rem;opacity:0.6;margin-top:2.5rem;line-height:1.4'>"
        "Independent practice tool by Hajer Alshame. Not affiliated with the AICPA or NASBA. "
        "AI answers can contain mistakes, so check important points against the official standards. "
        "Please don't type personal information into the chat.</p>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Screen: QUESTION
# ---------------------------------------------------------------------------

def _load_next_task() -> None:
    """Fetch or generate the next task and store in session state."""
    wc = _get_watsonx_module()
    topic = st.session_state.topic
    minutes = st.session_state.session_minutes

    # Per-topic exclusion list — prevents repeating any task within the session
    by_topic: dict = st.session_state.used_task_ids_by_topic
    exclude = by_topic.get(topic, [])

    task, is_ai = wc.generate_task(topic, minutes, exclude)
    st.session_state.current_task = task
    st.session_state.is_ai_task = is_ai
    st.session_state.user_choice = None
    st.session_state.feedback_text = None
    st.session_state.chat_history = []  # new task, fresh chat
    st.session_state.chat_error = None

    # Record the used ID under this topic
    by_topic.setdefault(topic, []).append(task["id"])
    st.session_state.used_task_ids_by_topic = by_topic


def screen_question() -> None:
    # Load task if not yet loaded for this question
    if st.session_state.current_task is None:
        with st.spinner("Your manager is preparing your task…"):
            _load_next_task()

    task = st.session_state.current_task
    q_num = st.session_state.questions_done + 1
    q_limit = st.session_state.question_limit

    # ----- progress -----
    progress_pct = (st.session_state.questions_done) / q_limit
    st.progress(progress_pct)
    st.markdown(
        f'<p class="progress-label">Question {q_num} of {q_limit} '
        f'· Topic: {TOPICS[st.session_state.topic]} '
        f'· Score: {st.session_state.score}/{st.session_state.questions_done}</p>',
        unsafe_allow_html=True,
    )

    # ----- Boss banner -----
    st.markdown(
        '<div class="boss-banner">'
        '<strong>👔 Your Manager (Boss Mode)</strong><br>'
        'Review the following work prepared by a junior staff member. '
        'Identify the error and select the best correction.'
        '</div>',
        unsafe_allow_html=True,
    )

    # ----- Scenario -----
    st.markdown(f'<div class="scenario-box">{task["scenario"]}</div>', unsafe_allow_html=True)

    # ----- Question -----
    st.markdown(f"**{task['question']}**")

    options = task["options"]
    option_labels = [f"{k}. {v}" for k, v in sorted(options.items())]

    choice = st.radio(
        label="Select your answer:",
        options=sorted(options.keys()),
        format_func=lambda k: f"{k}. {options[k]}",
        key=f"answer_radio_{q_num}",
        index=None,
    )

    col1, col2 = st.columns([1, 3])
    with col1:
        submit_disabled = choice is None
        if st.button(
            "✔ Submit Answer",
            type="primary",
            disabled=submit_disabled,
            use_container_width=True,
        ):
            st.session_state.user_choice = choice
            st.session_state.screen = "feedback"
            st.rerun()

    if st.session_state.is_ai_task:
        st.caption("✨ Question generated live by IBM Granite via watsonx.ai.")
    else:
        st.caption("📚 Practice bank — written with IBM Bob.")


# ---------------------------------------------------------------------------
# Screen: FEEDBACK
# ---------------------------------------------------------------------------

def _build_feedback_text(task: dict, user_choice: str) -> str:
    """Compose structured coaching feedback from the task explanation data."""
    correct = task["correct"]
    options = task["options"]
    exp = task["explanation"]
    is_correct = user_choice == correct

    result_line = (
        "✅ Correct! Well done."
        if is_correct
        else f"❌ Not quite. You chose {user_choice}; the correct answer is {correct}."
    )

    lines = [result_line, ""]

    # Correct reason
    lines.append(f"**Why {correct} is correct:**")
    lines.append(exp["correct_reason"])
    lines.append("")

    # Wrong options
    lines.append("**Why the other options are wrong:**")
    for letter in ["A", "B", "C", "D"]:
        if letter == correct:
            continue
        why_key = f"why_not_{letter}"
        why = exp.get(why_key, "")
        if why and "n/a" not in why.lower():
            lines.append(f"- **{letter}. {options[letter]}** — {why}")
    lines.append("")

    # Tip
    lines.append(f"💡 **Exam tip:** {exp['tip']}")

    return "\n".join(lines)


def screen_feedback() -> None:
    task = st.session_state.current_task
    user_choice = st.session_state.user_choice
    correct = task["correct"]
    is_correct = user_choice == correct

    q_num = st.session_state.questions_done + 1
    q_limit = st.session_state.question_limit

    # Update score tracking (only once per question)
    if st.session_state.feedback_text is None:
        if is_correct:
            st.session_state.score += 1
        else:
            st.session_state.missed_items.append({
                "topic_display": TOPICS[st.session_state.topic],
                "tip": task["explanation"].get("tip", ""),
            })
        st.session_state.feedback_text = _build_feedback_text(task, user_choice)
        st.session_state.questions_done += 1

    # ----- progress -----
    progress_pct = st.session_state.questions_done / q_limit
    st.progress(progress_pct)
    st.markdown(
        f'<p class="progress-label">Question {q_num} of {q_limit} '
        f'· Score: {st.session_state.score}/{st.session_state.questions_done}</p>',
        unsafe_allow_html=True,
    )

    # ----- Coach banner -----
    result_label = "Correct ✅" if is_correct else "Incorrect ❌"
    st.markdown(
        f'<div class="coach-banner">'
        f'<strong>🎓 Your Coach — {result_label}</strong>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ----- Scenario recap -----
    with st.expander("📋 Review the task scenario", expanded=False):
        st.markdown(f'<div class="scenario-box">{task["scenario"]}</div>', unsafe_allow_html=True)

    # ----- Feedback -----
    box_class = "feedback-correct" if is_correct else "feedback-incorrect"
    # Render markdown properly by using st.markdown directly
    st.markdown(st.session_state.feedback_text)

    st.divider()
    _ask_the_coach(task, user_choice)

    st.divider()

    # ----- Navigation -----
    if st.session_state.questions_done >= q_limit:
        if st.button("📊 See Session Summary", type="primary", use_container_width=True):
            st.session_state.screen = "summary"
            st.rerun()
    else:
        if st.button("➡ Next Question", type="primary", use_container_width=True):
            st.session_state.current_task = None  # trigger load of next task
            st.session_state.screen = "question"
            st.rerun()


# ---------------------------------------------------------------------------
# Ask the Coach (AI chat about the current task, powered by Google Gemini)
# ---------------------------------------------------------------------------

def _send_to_coach(question: str, task: dict, user_choice: str) -> None:
    import coach_chat  # noqa: PLC0415

    history = st.session_state.chat_history
    history.append({"role": "user", "content": question})
    with st.spinner("The Coach is thinking…"):
        try:
            reply = coach_chat.ask_coach(task, user_choice, history)
        except Exception as e:  # noqa: BLE001
            history.pop()  # let the student try the same question again
            st.session_state.chat_error = str(e)
            return
    history.append({"role": "assistant", "content": reply})
    st.session_state.chat_error = None


def _ask_the_coach(task: dict, user_choice: str) -> None:
    import coach_chat  # noqa: PLC0415

    st.subheader("💬 Ask the Coach")
    if not coach_chat.is_available():
        st.info("Ask the Coach is turned off. Add a GEMINI_API_KEY to the app's secrets to turn it on.")
        return

    st.caption(
        "Still confused? Ask a follow-up question about this task. "
        "Answers are written live by AI (Google Gemini) and can make mistakes, "
        "so check anything important against the ASC standard."
    )

    history = st.session_state.chat_history
    for m in history:
        who = "You" if m["role"] == "user" else "Coach"
        with st.chat_message("user" if m["role"] == "user" else "assistant", avatar="🙋" if m["role"] == "user" else "🎓"):
            st.markdown(f"**{who}:** {m['content']}")

    if st.session_state.get("chat_error"):
        st.warning(st.session_state.chat_error)

    asked = sum(1 for m in history if m["role"] == "user")
    if asked >= coach_chat.MAX_TURNS_PER_TASK:
        st.caption("You've reached the question limit for this task. Move on to the next one!")
        return

    # One-tap starter questions
    wrong = user_choice != task["correct"]
    starters = [
        f"Why is my answer ({user_choice}) wrong?" if wrong else "Why is this right?",
        "Explain it more simply",
        "Give me a similar example",
    ]
    cols = st.columns(len(starters))
    for i, (col, q) in enumerate(zip(cols, starters)):
        if col.button(q, key=f"starter_{st.session_state.questions_done}_{i}_{asked}", use_container_width=True):
            _send_to_coach(q, task, user_choice)
            st.rerun()

    with st.form(key=f"coach_form_{st.session_state.questions_done}", clear_on_submit=True):
        question = st.text_area(
            "Type your question for the Coach:",
            placeholder="Example: Why isn't the full $24,000 revenue if the cash was already received?",
            max_chars=500,
            height=90,
        )
        if st.form_submit_button("Ask the Coach") and question.strip():
            _send_to_coach(question.strip(), task, user_choice)
            st.rerun()


# ---------------------------------------------------------------------------
# Screen: SUMMARY
# ---------------------------------------------------------------------------

def screen_summary() -> None:
    from collections import Counter

    score = st.session_state.score
    total = st.session_state.questions_done
    pct = int(score / total * 100) if total else 0
    elapsed_sec = int(time.time() - (st.session_state.session_start or time.time()))
    elapsed_min = elapsed_sec // 60
    elapsed_s = elapsed_sec % 60
    missed_items: list[dict] = st.session_state.missed_items

    st.title("📊 Session Summary")
    st.divider()

    # ── Score ──────────────────────────────────────────────────────────────
    st.subheader("Your Score")
    col1, col2, col3 = st.columns(3)
    col1.metric("Questions", total)
    col2.metric("Correct", score)
    col3.metric("Accuracy", f"{pct}%")
    st.markdown(f"⏱ Time elapsed: **{elapsed_min}m {elapsed_s:02d}s**")
    st.divider()

    # ── Missed topics table ────────────────────────────────────────────────
    st.subheader("Topics to Review")
    if not missed_items:
        st.success("🎉 Perfect session! No topics to review.")
    else:
        missed_counts = Counter(item["topic_display"] for item in missed_items)
        rows = "".join(
            f"<tr><td>{topic}</td><td style='text-align:center'>{count}</td></tr>"
            for topic, count in missed_counts.most_common()
        )
        st.markdown(
            f"""
            <table class="summary-table" role="table" aria-label="Missed topics table">
              <thead>
                <tr><th scope="col">Topic</th><th scope="col" style="text-align:center">Missed</th></tr>
              </thead>
              <tbody>{rows}</tbody>
            </table>
            """,
            unsafe_allow_html=True,
        )
    st.divider()

    # ── Your study plan ────────────────────────────────────────────────────
    st.subheader("📋 Your Study Plan")

    if not missed_items:
        st.markdown(
            "No weak areas detected this session. "
            "Consider extending to a 15-minute session or trying a different topic to stay sharp."
        )
    else:
        st.markdown(
            "Based on your missed questions, here are the key tips to review "
            "and a suggested next session:"
        )

        # Deduplicate tips per topic (keep first occurrence to avoid repetition)
        seen_tips: set = set()
        tip_rows = []
        for item in missed_items:
            tip = item["tip"]
            topic_d = item["topic_display"]
            key = (topic_d, tip)
            if key not in seen_tips:
                seen_tips.add(key)
                tip_rows.append((topic_d, tip))

        for topic_d, tip in tip_rows:
            st.markdown(f"- **{topic_d}:** {tip}")

        st.markdown("")

        # Suggest next session: weakest topic + length that gives enough questions
        weakest_topic_display, _ = missed_counts.most_common(1)[0]
        # Find the topic key from display name
        weakest_topic_key = next(
            (k for k, v in TOPICS.items() if v == weakest_topic_display),
            st.session_state.topic,
        )
        # Suggest 10 or 15 minutes based on current score
        suggested_minutes = 10 if pct >= 50 else 15
        suggested_q = SESSION_LENGTHS[suggested_minutes]
        st.info(
            f"**Suggested next session:** {weakest_topic_display} · "
            f"{suggested_minutes} minutes (~{suggested_q} questions). "
            f"Focus on the exam tips above before starting."
        )

    st.divider()

    # ── Encouragement ─────────────────────────────────────────────────────
    if pct == 100:
        st.balloons()
        st.success("Outstanding work! You nailed every question.")
    elif pct >= 70:
        st.success("Good job! Keep practicing to reach exam-ready level (≥75%).")
    else:
        st.warning("Keep going — consistent practice builds the pattern recognition you need.")

    if st.button("🔄 Start New Session", type="primary", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

SCREENS = {
    "setup": screen_setup,
    "question": screen_question,
    "feedback": screen_feedback,
    "summary": screen_summary,
}

SCREENS[st.session_state.screen]()

