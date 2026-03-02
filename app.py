import json
import sqlite3
import streamlit as st
from openai import OpenAI

st.set_page_config(page_title="Writing Performance Analyzer", layout="centered")
st.title("AI Writing Performance Analyzer (Students)")

# ---------- OpenAI ----------
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

ANALYTICS_INSTRUCTIONS = """
You are a Quantitative Performance Analytics Agent for Saudi EFL writing.
Return ONLY valid JSON. No extra text.

Compute:
- word_count
- sentence_count
- grammar_error_count (explicit count)
- lexical_error_count (explicit count)
- cohesion_issue_count (explicit count)
- total_error_count
- error_density = total_error_count / word_count (round to 3 decimals)
- error_type_ranking: top 5 error types with counts
Score 0–4:
accuracy, lexis, coherence, task_achievement, style_voice

Return JSON exactly:
{
 "word_count":0,
 "sentence_count":0,
 "grammar_error_count":0,
 "lexical_error_count":0,
 "cohesion_issue_count":0,
 "total_error_count":0,
 "error_density":0.000,
 "error_type_ranking":[{"type":"","count":0}],
 "rubric_scores":{"accuracy":0,"lexis":0,"coherence":0,"task_achievement":0,"style_voice":0},
 "top_3_fixes":["","",""],
 "next_task":{"prompt":"","culture_anchor":"Saudi context"}
}
"""

# ---------- Local DB (SQLite) ----------
conn = sqlite3.connect("writing_data.db", check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  student_id TEXT NOT NULL,
  attempt_no INTEGER NOT NULL,
  task_prompt TEXT,
  culture_anchor TEXT,
  student_text TEXT,
  result_json TEXT
)
""")
conn.commit()

# ---------- UI ----------
with st.form("form"):
    student_id = st.text_input("Student ID (رمز الطالب) *")
    attempt_no = st.number_input("Attempt No (رقم المحاولة)", min_value=1, step=1, value=1)
    task_prompt = st.text_area("Task prompt (سؤال الكتابة)")
    culture_anchor = st.text_input("Saudi culture anchor (مرتكز ثقافي سعودي)")
    student_text = st.text_area("Student writing (نص الطالب) *", height=220)
    submitted = st.form_submit_button("Analyze & Save")

if submitted:
    if not student_id.strip() or not student_text.strip():
        st.warning("اكتبي رمز الطالب + النص.")
        st.stop()

    prompt = f"""
Task prompt: {task_prompt}
Culture anchor: {culture_anchor}

Student text:
{student_text}

Return ONLY JSON.
"""

    try:
        resp = client.responses.create(
            model="gpt-4.1-mini",
            instructions=ANALYTICS_INSTRUCTIONS,
            input=prompt,
            temperature=0.2,
        )
        raw = resp.output_text.strip()
        result = json.loads(raw)
    except Exception as e:
        st.error("صار خطأ أثناء التحليل. افتحي Logs لمعرفة التفاصيل.")
        st.code(str(e))
        st.stop()

    cur.execute(
        "INSERT INTO attempts (student_id, attempt_no, task_prompt, culture_anchor, student_text, result_json) VALUES (?,?,?,?,?,?)",
        (student_id.strip(), int(attempt_no), task_prompt, culture_anchor, student_text, json.dumps(result)),
    )
    conn.commit()

    st.success("تم التحليل والحفظ ✅")
    st.json(result)

st.divider()
st.subheader("Research view (latest saved attempts)")
rows = cur.execute(
    "SELECT created_at, student_id, attempt_no, result_json FROM attempts ORDER BY id DESC LIMIT 10"
).fetchall()

if rows:
    for created_at, sid, att, rj in rows:
        st.caption(f"{created_at} | {sid} | Attempt {att}")
        st.json(json.loads(rj))
else:
    st.info("لا توجد بيانات محفوظة بعد.")
