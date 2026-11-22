# CPA Boss Coach

A study assistant for the CPA FAR exam, built with **Python + Streamlit**.  
The *Boss* hands you a realistic accounting scenario with one hidden error.  
You pick the fix. The *Coach* explains every option — right and wrong — so you build real exam intuition.

> **Built with IBM Bob.** Every stage of this project — planning, code generation, bug fixing, task writing, and testing — was completed with IBM Bob as the primary development tool. See [How IBM Bob was used](#how-ibm-bob-was-used) below.

---

## Features

- **24 hand-crafted FAR tasks** — 6 per topic, each a realistic 'junior accountant' scenario
- **4 FAR topics:** Revenue Recognition (ASC 606), Leases (ASC 842), Inventory (ASC 330), Bonds & Debt (ASC 835 / ASC 470)
- **3 session lengths:** 5 / 10 / 15 minutes
- **No-repeat guarantee:** tasks within a session are never repeated until all 6 for a topic are exhausted
- **Shuffled answer options** every time — the correct letter varies so you can't pattern-match
- **Full "Why not the others?" coaching** — explanation for every option, plus an ASC-cited exam tip
- **Session summary + study plan** — score, accuracy, missed tips per topic, and a suggested next session
- **Optional IBM watsonx.ai / Granite** — generates extra tasks on the fly if credentials are configured; falls back to the task bank automatically
- **Accessible UI** — semantic headings, screen-reader labels, `aria` table attributes, no color-only information

---

## Project Structure

```
CPA-Study-Assistant/
├── app.py                  # Streamlit app — UI, routing, session logic
├── watsonx_client.py       # Task delivery: task bank (default) + optional watsonx.ai
├── prompts.py              # Prompt templates for IBM Granite (optional AI mode)
├── task_bank.json          # 24 hand-written FAR tasks (6 per topic), written with IBM Bob
├── requirements.txt
├── .env.example            # Credential template — copy to .env
└── README.md
```

---

## Quick Start (Local)

### 1. Prerequisites

- Python 3.9+ (tested on Python 3.14)

### 2. Clone and set up

```bash
git clone <your-repo-url>
cd CPA-Study-Assistant

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Run (no API keys needed)

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`.  
All 24 tasks work immediately with no credentials required.

### 4. Configure IBM watsonx.ai (optional — for AI-generated tasks)

```bash
cp .env.example .env
```

Edit `.env`:

```env
WATSONX_APIKEY=your_ibm_cloud_api_key
WATSONX_PROJECT_ID=your_watsonx_project_id
WATSONX_URL=https://us-south.ml.cloud.ibm.com
```

When credentials are present, the app generates additional tasks using **IBM Granite** (`ibm/granite-3-3-8b-instruct`). Questions from the task bank are still used as the fallback on any error.

---

## Deploy to Streamlit Community Cloud (Free)

1. Push to a public GitHub repo (`.env` is in `.gitignore` — safe to push).
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app** → select your repo → `app.py`.
3. *(Optional)* Under **Advanced settings → Secrets**, add your watsonx credentials:

```toml
WATSONX_APIKEY = "..."
WATSONX_PROJECT_ID = "..."
WATSONX_URL = "https://us-south.ml.cloud.ibm.com"
```

4. Click **Deploy**. Done — the app runs fully on the task bank even without secrets.

---

## How IBM Bob Was Used

IBM Bob was the sole development tool used throughout this project. Here is how each stage was completed:

### 1. Planning and architecture

Bob was used to design the full application architecture before a single line of code was written:
- Decided on the Boss/Coach persona model for the UX
- Defined the JSON schema for tasks (`scenario`, `question`, `options`, `correct`, `explanation` with `why_not_X` keys)
- Planned the five-screen Streamlit flow (setup → question → feedback → summary → reset)
- Identified the need for a task-bank fallback, option shuffling, and per-topic no-repeat logic

### 2. Code generation

Bob generated all source files from scratch:
- `app.py` — full Streamlit UI with CSS, session-state routing, accessible HTML tables
- `watsonx_client.py` — credential loading, watsonx.ai API integration, JSON validation, `shuffle_options()`
- `prompts.py` — structured prompt templates for task generation and feedback via Granite

### 3. Bug fixing

Two bugs were caught and fixed by Bob during review:
- **Validation over-strictness:** `_validate_task` required `why_not_X` for all four letters, including the correct one. Fixed to only require it for the three wrong options.
- **Predictable correct answer:** 7 of 8 original tasks had `"correct": "B"`. Bob added `shuffle_options()` to randomly reassign letters before display, correctly remapping `correct` and all `why_not_X` explanation keys.

### 4. Writing the task bank

Bob wrote all 24 FAR tasks in `task_bank.json`:
- Each task is a realistic "junior accountant at a firm" scenario with exactly one accounting error
- Each task includes four plausible options, one correct answer, and full explanations citing the relevant ASC codification
- Bob double-checked all accounting numbers, PV calculations, and GAAP rules for accuracy
- Bob also reviewed and corrected a circular-reasoning error in `bonds_6` options A and C before finalisation

### 5. Testing and validation

Bob ran a Python validation script to confirm:
- JSON is well-formed
- All 24 tasks have correct schema (required keys, valid `correct` letter, `why_not_X` for each wrong option)
- 6 tasks per topic
- Headless `streamlit run app.py` returns HTTP 200

---

## Getting IBM watsonx.ai Credentials (Optional)

1. Create a free [IBM Cloud account](https://cloud.ibm.com/registration).
2. Provision a **watsonx.ai** instance (Lite tier is free).
3. Create a **project** in watsonx.ai and copy the Project ID.
4. Generate an **API key** at *Manage → Access → API keys*.
5. The `WATSONX_URL` is typically `https://us-south.ml.cloud.ibm.com` for the Dallas region.

---

## License

MIT

## New: Ask the Coach (AI chatbot)

After each task, students can ask the Coach follow-up questions, such as
"Why is my answer wrong?", "Explain this more simply" or "Give me a similar example".

- Powered by Google Gemini through the `google-genai` SDK (`coach_chat.py`).
- Every question is sent together with the current task, its correct answer and the
  official "Why not the others?" explanations, so answers stay grounded in that task
  (a simple retrieval-augmented approach).
- Limited to 8 questions per task to stay within the free quota.
- If no key is set, the app still works and simply shows that Ask the Coach is off.

### Setup
1. Create a free API key at Google AI Studio (aistudio.google.com).
2. Add it to Streamlit secrets (or a local `.env` file):

```toml
GEMINI_API_KEY = "your-key-here"
# optional: GEMINI_MODEL = "a-specific-model-name"
```
