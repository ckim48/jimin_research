# app.py
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import random
from datetime import datetime
import csv
import re

app = Flask(__name__)
app.secret_key = "change-this-to-a-random-secret"

DB_PATH = "static/research.db"
GROUPA_CSV_PATH = "groupa.csv"

@app.route('/result', methods = ["GET", "POST"])
def result():
    if request.method == "POST":
        q1 = request.form.get("question1")
        q2 = request.form.get("question2")
        q3 = request.form.get("question3")
        q4 = request.form.get("question4")
        q5 = request.form.get("question5")

        return redirect(url_for("completed"))
    return render_template('result.html')

@app.route("/completed", methods = ["GET"])
def completed():
    return render_template('completed.html')
# -------------------------
# DB helpers / setup
# -------------------------
def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(cur, name: str) -> bool:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def ensure_tables():
    """
    Creates tables if missing.
    Also migrates older DBs to add missing columns needed for the equation-builder version.
    """
    db = db_conn()
    cur = db.cursor()

    # --- participants ---
    if not table_exists(cur, "participants"):
        cur.execute("""
            CREATE TABLE IF NOT EXISTS participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                access_code TEXT,
                age INTEGER,
                gender TEXT,
                group_name TEXT,
                created_at TEXT,
                finished_at TEXT NOT NULL
            )
        """)
    else:
        cur.execute("PRAGMA table_info(participants)")
        cols = {row["name"] for row in cur.fetchall()}
        if "access_code" not in cols:
            cur.execute("ALTER TABLE participants ADD COLUMN access_code TEXT")

    # --- responses ---
    if not table_exists(cur, "responses"):
        cur.execute("""
            CREATE TABLE IF NOT EXISTS responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                participant_id INTEGER NOT NULL,
                task_name TEXT NOT NULL,
                q_index INTEGER NOT NULL,
                category TEXT,
                numbers_text TEXT,
                ops_text TEXT,
                target REAL,
                option_a TEXT,
                option_b TEXT,
                option_c TEXT,
                chosen TEXT,
                is_correct INTEGER,
                rt_ms INTEGER,
                created_at TEXT NOT NULL,
                expr_text TEXT,
                result_val REAL,
                FOREIGN KEY(participant_id) REFERENCES participants(id)
            )
        """)
    else:
        cur.execute("PRAGMA table_info(responses)")
        cols = {row["name"] for row in cur.fetchall()}
        if "expr_text" not in cols:
            cur.execute("ALTER TABLE responses ADD COLUMN expr_text TEXT")
        if "result_val" not in cols:
            cur.execute("ALTER TABLE responses ADD COLUMN result_val REAL")

    db.commit()
    db.close()


ensure_tables()



_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")

def parse_numbers_field(s: str):
    if not s:
        return []
    s = str(s).strip()
    nums = _NUM_RE.findall(s)
    out = []
    for x in nums:
        try:
            out.append(float(x))
        except Exception:
            continue
    return out


def parse_ops_field(s: str):
    if not s:
        return []
    s = str(s).strip().replace("×", "*")
    parts = [p.strip() for p in s.split(",")] if "," in s else [p.strip() for p in s.split()]
    parts = [p for p in parts if p]

    allowed = {"+", "-", "*", "/", "//", "%", "^"}
    ops = []
    for p in parts:
        p = re.sub(r"\s+", "", p)
        if p in allowed:
            ops.append(p)
            continue

        tmp = p
        while tmp:
            if tmp.startswith("//"):
                ops.append("//")
                tmp = tmp[2:]
            elif tmp[0] in "+-*/%^":
                ops.append(tmp[0])
                tmp = tmp[1:]
            else:
                tmp = tmp[1:]

    seen = set()
    out = []
    for op in ops:
        if op in allowed and op not in seen:
            out.append(op)
            seen.add(op)
    return out


def normalize_ops_text_for_display(ops_list):
    return ", ".join(ops_list)


def normalize_numbers_text_for_display(nums_list):
    def fmt(x):
        if abs(x - int(x)) < 1e-12:
            return str(int(x))
        return str(x)
    return ", ".join(fmt(x) for x in nums_list)


# -------------------------
# Question loading
# -------------------------
def load_groupA_questions():
    questions = []
    with open(GROUPA_CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        last_cat = None

        for row in reader:
            if not row:
                continue

            cat = (row.get("category") or "").strip()
            if cat:
                last_cat = cat
            else:
                cat = last_cat or "-"

            numbers_raw = (row.get("Numbers") or "").strip()
            ops_raw = (row.get("Operations") or "").strip()
            target_raw = (row.get("Target") or "").strip()
            answer = (row.get("Answer") or "").strip()

            if not numbers_raw or not ops_raw or target_raw == "":
                continue

            nums = parse_numbers_field(numbers_raw)
            ops = parse_ops_field(ops_raw)

            if not nums or not ops:
                continue

            try:
                target_val = float(target_raw)
            except Exception:
                continue

            numbers_text = normalize_numbers_text_for_display(nums)
            ops_text = normalize_ops_text_for_display(ops)

            questions.append({
                "category": cat,
                "numbers_text": numbers_text,
                "ops_text": ops_text,
                "numbers": nums,
                "ops": ops,
                "target": target_val,
                "answer": answer
            })

    return questions


# -------------------------
# Routes
# -------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        access_code = request.form.get("access_code", "").strip()
        gender = request.form.get("gender", "").strip()
        age_raw = request.form.get("age", "").strip()
        age = int(age_raw) if age_raw.isdigit() else None

        group = "A" if random.random() <= 0.5 else "B"
        now = datetime.utcnow().isoformat()

        db = db_conn()
        cur = db.cursor()
        cur.execute(
            """
            INSERT INTO participants (access_code, age, gender, group_name, created_at, finished_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (access_code, age, gender, group, now, "no")
        )
        participant_id = cur.lastrowid
        db.commit()
        db.close()

        session["participant_id"] = participant_id
        session["group_name"] = group

        return redirect(url_for("taskA" if group == "A" else "taskB"))

    return render_template("index.html")


@app.route("/taskA")
def taskA():
    session["taskA_index"] = 0
    return render_template("taskA.html")


@app.route("/taskB")
def taskB():
    return render_template("taskB.html")



@app.route("/api/taskA/next")
def api_taskA_next():
    participant_id = session.get("participant_id")
    if not participant_id:
        return jsonify({"error": "no participant"}), 401

    questions = load_groupA_questions()
    idx = int(session.get("taskA_index", 0))

    if idx >= len(questions):
        db = db_conn()
        db.execute(
            "UPDATE participants SET finished_at=? WHERE id=?",
            (datetime.utcnow().isoformat(), participant_id)
        )
        db.commit()
        db.close()
        return jsonify({"done": True})

    q = questions[idx]

    return jsonify({
        "done": False,
        "q_index": idx,
        "total": len(questions),
        "category": q["category"],
        "numbers_text": q["numbers_text"],
        "ops_text": q["ops_text"],
        "numbers": q["numbers"],
        "ops": q["ops"],
        "target": q["target"],
    })


@app.route("/api/taskA/submit", methods=["POST"])
def api_taskA_submit():
    participant_id = session.get("participant_id")
    if not participant_id:
        return jsonify({"error": "no participant"}), 401

    data = request.get_json(force=True) or {}
    q_index = int(data.get("q_index", -1))

    questions = load_groupA_questions()
    if q_index < 0 or q_index >= len(questions):
        return jsonify({"error": "bad q_index"}), 400

    q = questions[q_index]

    chosen = data.get("chosen")
    rt_ms = data.get("rt_ms")
    expr_text = (data.get("expr") or "").strip()
    result_val = data.get("result")

    try:
        rt_ms = int(rt_ms) if rt_ms is not None else None
    except Exception:
        rt_ms = None

    try:
        result_val = float(result_val) if result_val is not None else None
    except Exception:
        result_val = None

    is_correct = 0
    if result_val is not None and abs(result_val - float(q["target"])) < 1e-9:
        is_correct = 1

    db = db_conn()
    db.execute(
        """
        INSERT INTO responses
          (participant_id, task_name, q_index, category, numbers_text, ops_text, target,
           option_a, option_b, option_c, chosen, is_correct, rt_ms, created_at, expr_text, result_val)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            participant_id, "A", q_index,
            q["category"], q["numbers_text"], q["ops_text"], q["target"],
            None, None, None,
            chosen, is_correct, rt_ms, datetime.utcnow().isoformat(),
            expr_text, result_val
        )
    )
    db.commit()
    db.close()

    session["taskA_index"] = q_index + 1
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True)
