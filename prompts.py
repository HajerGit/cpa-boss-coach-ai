"""
Prompt templates for the CPA Boss Coach application.
"""

TASK_GENERATION_PROMPT = """\
You are generating a CPA exam study task for the FAR section.

Topic: {topic}
Session length hint: {session_minutes} minutes

Your job: produce ONE realistic work task formatted as a JSON object (and NOTHING else — no markdown, no explanation, no extra text outside the JSON).

The task must follow this exact JSON schema:
{{
  "id": "generated_1",
  "topic": "{topic}",
  "scenario": "<2-4 sentence scene-setting as a memo from a manager, then the flawed journal entry or schedule as plain text>",
  "question": "<one clear multiple-choice stem asking what is WRONG>",
  "options": {{
    "A": "<option text>",
    "B": "<option text>",
    "C": "<option text>",
    "D": "<option text>"
  }},
  "correct": "<single letter A, B, C, or D>",
  "explanation": {{
    "correct_reason": "<why the correct answer is right, citing the relevant standard>",
    "why_not_A": "<why option A is wrong (or if A is correct, fill the other three)>",
    "why_not_B": "<why option B is wrong>",
    "why_not_C": "<why option C is wrong>",
    "why_not_D": "<why option D is wrong>",
    "tip": "<one sentence exam tip on how to distinguish the correct answer>"
  }}
}}

Rules:
- The scenario must contain exactly ONE accounting error.
- Options must include the correct answer plus three plausible distractors.
- Cite the relevant US GAAP codification (ASC) in the correct_reason.
- Never skip the "why_not_X" field for the correct option; write "N/A — this is the correct answer." for that field.
- Output raw JSON only. No markdown code fences.
"""

FEEDBACK_PROMPT = """\
You are a CPA exam coach explaining why a student's answer choice is {result}.

Topic: {topic}
Scenario summary: {scenario_summary}
Correct answer: Option {correct} — {correct_text}
Student chose: Option {student_choice} — {student_text}

Explanation data:
- Correct reason: {correct_reason}
- Why not A: {why_not_A}
- Why not B: {why_not_B}
- Why not C: {why_not_C}
- Why not D: {why_not_D}
- Exam tip: {tip}

Write a concise coaching response (plain text, no markdown headers):
1. One sentence acknowledging whether they got it right or wrong.
2. Explain WHY the correct answer is right (reference the standard).
3. Briefly explain why each wrong option fails (one sentence each).
4. Close with the exam tip.
Keep the total response under 200 words. Be direct and educational.
"""
