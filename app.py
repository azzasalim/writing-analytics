import json
import sqlite3
import streamlit as st
from openai import OpenAI
import hashlib
st.set_page_config(page_title="Writing Performance Analyzer", layout="centered")
st.title("AI Writing Performance Analyzer (Students)")
# ---------- Simple Auth (Student/Admin) ----------
if "role" not in st.session_state:
    st.session_state.role = None
if "student_id" not in st.session_state:
    st.session_state.student_id = None

st.sidebar.title("Login")

who = st.sidebar.radio("Role", ["Student", "Admin"])

if who == "Admin":
    admin_pw = st.sidebar.text_input("Admin password", type="password")
    if st.sidebar.button("Login (Admin)"):
        if admin_pw == st.secrets.get("ADMIN_PASSWORD", ""):
            st.session_state.role = "admin"
            st.session_state.student_id = None
            st.sidebar.success("Admin logged in ✅")
        else:
            st.sidebar.error("Wrong password")

if who == "Student":
    sid = st.sidebar.text_input("Student ID", placeholder="e.g., E01")
    pin = st.sidebar.text_input("PIN", type="password")

    if st.sidebar.button("Login (Student)"):
        if not sid.strip() or not pin.strip():
            st.sidebar.error("Enter Student ID and PIN")
        else:
            sid = sid.strip()
            row = cur.execute("SELECT pin_hash FROM students WHERE student_id=?", (sid,)).fetchone()

            if row is None:
                # First-time registration
                cur.execute("INSERT INTO students (student_id, pin_hash) VALUES (?,?)", (sid, hash_pin(pin)))
                conn.commit()
                st.session_state.role = "student"
                st.session_state.student_id = sid
                st.sidebar.success("Registered & logged in ✅")
            else:
                if row[0] == hash_pin(pin):
                    st.session_state.role = "student"
                    st.session_state.student_id = sid
                    st.sidebar.success("Logged in ✅")
                else:
                    st.sidebar.error("Wrong PIN")

st.sidebar.divider()
if st.sidebar.button("Logout"):
    st.session_state.role = None
    st.session_state.student_id = None
    st.sidebar.success("Logged out")
    # ---------- Block access if not logged in ----------
if st.session_state.role is None:
    st.info("Please login from the sidebar.")
    st.stop()
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
# ---------- Students table (for PIN login) ----------
cur.execute("""
CREATE TABLE IF NOT EXISTS students (
  student_id TEXT PRIMARY KEY,
  pin_hash TEXT NOT NULL
)
""")
conn.commit()

def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()
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
st.divider()
st.subheader("Student Growth Analysis")

student_lookup = st.text_input("Enter Student ID to analyze growth")

if student_lookup:
    rows = cur.execute(
        "SELECT attempt_no, result_json FROM attempts WHERE student_id=? ORDER BY attempt_no ASC",
        (student_lookup,)
    ).fetchall()

    if len(rows) >= 2:
        scores = []
        for attempt_no, rj in rows:
            data = json.loads(rj)
            total_score = sum(data["rubric_scores"].values())
            scores.append((attempt_no, total_score))

        first_score = scores[0][1]
        last_score = scores[-1][1]
        improvement = last_score - first_score
        improvement_percent = round((improvement / max(1, first_score)) * 100, 2)

        if improvement_percent < 10:
            speed = "Slow"
        elif improvement_percent < 25:
            speed = "Moderate"
        else:
            speed = "Fast"

        st.write("First Score:", first_score)
        st.write("Last Score:", last_score)
        st.write("Improvement %:", improvement_percent)
        st.write("Learning Speed:", speed)
    else:
        st.info("Need at least 2 attempts for growth analysis.")
st.divider()
st.subheader("Admin Dashboard")

all_rows = cur.execute("SELECT result_json FROM attempts").fetchall()

if all_rows:
    total_attempts = len(all_rows)
    total_students = cur.execute("SELECT COUNT(DISTINCT student_id) FROM attempts").fetchone()[0]

    total_scores = []
    total_error_density = []

    for (rj,) in all_rows:
        data = json.loads(rj)
        total_scores.append(sum(data["rubric_scores"].values()))
        total_error_density.append(data["error_density"])

    avg_score = round(sum(total_scores) / len(total_scores), 2)
    avg_error_density = round(sum(total_error_density) / len(total_error_density), 3)

    st.write("Total Students:", total_students)
    st.write("Total Attempts:", total_attempts)
    st.write("Average Total Score:", avg_score)
    st.write("Average Error Density:", avg_error_density)
else:
    st.info("No data yet.")
import matplotlib.pyplot as plt

st.divider()
st.subheader("Student Progress Chart (Attempts vs Total Score)")

student_chart_id = st.text_input("Student ID for chart (رمز الطالب للرسم البياني)")

if student_chart_id:
    rows = cur.execute(
        "SELECT attempt_no, result_json FROM attempts WHERE student_id=? ORDER BY attempt_no ASC",
        (student_chart_id.strip(),)
    ).fetchall()

    if len(rows) >= 2:
        attempts = []
        total_scores = []
        error_densities = []

        for attempt_no, rj in rows:
            data = json.loads(rj)
            total_score = sum(data["rubric_scores"].values())
            attempts.append(attempt_no)
            total_scores.append(total_score)
            error_densities.append(data.get("error_density", 0.0))

        fig = plt.figure()
        plt.plot(attempts, total_scores, marker="o")
        plt.xlabel("Attempt No")
        plt.ylabel("Total Rubric Score (0–20)")
        plt.title(f"Progress for {student_chart_id}")
        st.pyplot(fig)

        fig2 = plt.figure()
        plt.plot(attempts, error_densities, marker="o")
        plt.xlabel("Attempt No")
        plt.ylabel("Error Density")
        plt.title(f"Error Density Trend for {student_chart_id}")
        st.pyplot(fig2)
    else:
        st.info("احتاج محاولتين على الأقل لعرض المنحنى.")
st.divider()
st.subheader("Normalized Gain (Learning Effectiveness)")

gain_student_id = st.text_input("Student ID for Gain Calculation")

if gain_student_id:
    rows = cur.execute(
        "SELECT attempt_no, result_json FROM attempts WHERE student_id=? ORDER BY attempt_no ASC",
        (gain_student_id.strip(),)
    ).fetchall()

    if len(rows) >= 2:
        scores = []
        for attempt_no, rj in rows:
            data = json.loads(rj)
            total_score = sum(data["rubric_scores"].values())
            scores.append(total_score)

        first_score = scores[0]
        last_score = scores[-1]
        max_score = 20

        if max_score - first_score != 0:
            g = round((last_score - first_score) / (max_score - first_score), 3)
        else:
            g = 0

        if g < 0.3:
            level = "Low Gain"
        elif g < 0.7:
            level = "Moderate Gain"
        else:
            level = "High Gain"

        st.write("First Score:", first_score)
        st.write("Last Score:", last_score)
        st.write("Normalized Gain (g):", g)
        st.write("Gain Level:", level)
    else:
        st.info("Need at least 2 attempts to calculate Gain.")
st.divider()
st.subheader("Admin Dashboard")

all_rows = cur.execute("SELECT result_json FROM attempts").fetchall()

if all_rows:
    total_attempts = len(all_rows)
    total_students = cur.execute("SELECT COUNT(DISTINCT student_id) FROM attempts").fetchone()[0]

    total_scores = []
    total_error_density = []

    for (rj,) in all_rows:
        data = json.loads(rj)
        total_scores.append(sum(data["rubric_scores"].values()))
        total_error_density.append(data["error_density"])

    avg_score = round(sum(total_scores) / len(total_scores), 2)
    avg_error_density = round(sum(total_error_density) / len(total_error_density), 3)

    st.write("Total Students:", total_students)
    st.write("Total Attempts:", total_attempts)
    st.write("Average Total Score:", avg_score)
    st.write("Average Error Density:", avg_error_density)
else:
    st.info("No data yet.")
st.divider()
st.subheader("Group Normalized Gain Analysis")

students = cur.execute("SELECT DISTINCT student_id FROM attempts").fetchall()
gains = []

for (sid,) in students:
    rows = cur.execute(
        "SELECT attempt_no, result_json FROM attempts WHERE student_id=? ORDER BY attempt_no ASC",
        (sid,)
    ).fetchall()

    if len(rows) >= 2:
        scores = []
        for attempt_no, rj in rows:
            data = json.loads(rj)
            scores.append(sum(data["rubric_scores"].values()))

        first_score = scores[0]
        last_score = scores[-1]
        max_score = 20

        if (max_score - first_score) != 0:
            g = (last_score - first_score) / (max_score - first_score)
            gains.append(g)

if gains:
    avg_gain = round(sum(gains) / len(gains), 3)
    high = len([g for g in gains if g >= 0.7])
    moderate = len([g for g in gains if 0.3 <= g < 0.7])
    low = len([g for g in gains if g < 0.3])

    st.write("Average Normalized Gain (g):", avg_gain)
    st.write("High Gain Students:", high)
    st.write("Moderate Gain Students:", moderate)
    st.write("Low Gain Students:", low)
else:
    st.info("Not enough multi-attempt students for group gain analysis.")
import matplotlib.pyplot as plt
import numpy as np

st.divider()
st.subheader("Distribution of Normalized Gain (Group Histogram)")

if gains:
    gains_array = np.array(gains)
    mean_gain = np.mean(gains_array)

    fig = plt.figure()
    plt.hist(gains_array, bins=6, edgecolor="black")
    plt.axvline(mean_gain)
    plt.xlabel("Normalized Gain (g)")
    plt.ylabel("Number of Students")
    plt.title("Histogram of Learning Gain Distribution")

    st.pyplot(fig)

    st.write("Group Mean Gain:", round(mean_gain, 3))
else:
    st.info("Not enough data for histogram.")
