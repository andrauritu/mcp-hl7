import re
from flask import Flask, jsonify, request

from db import init_db, get_conn

app = Flask(__name__)
init_db()

@app.get('/health')
def health():
    return jsonify(status="ok") 

@app.post('/patients')
def create_patient():
    body = request.get_json(force=True)

    name = str(body.get("name", "")).strip()
    dob = str(body.get("dob", "")).strip()
    sex = str(body.get("sex", "")).strip().upper()

    if not name or not dob or sex not in {"M", "F", "U"}:
        return jsonify(
            error = "invalid_input",
            expected = {"name": "string", "dob": "YYYY-MM-DD", "sex": "M|F|O"},
        ), 400
    
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO patients (name, dob, sex) VALUES (?, ?, ?)",
            (name, dob, sex),
        )

        patient_id = cur.lastrowid

        row = conn.execute(
            "SELECT id, name, dob, sex, created_at FROM patients WHERE id = ?",
            (patient_id,),
        ).fetchone()

    return jsonify(dict(row)), 201

@app.get('/patients/<int:patient_id>')
def get_patient(patient_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, name, dob, sex, created_at FROM patients WHERE id = ?",
            (patient_id,),
        ).fetchone()

    if row is None:
        return jsonify(error="patient_not_found"), 404
    
    return jsonify(dict(row))


@app.get("/icd/search")
def icd_search():
    q = str(request.args.get("q", "")).strip()
    limit_raw = request.args.get("limit") or "5"

    try:
        limit = int(limit_raw)
    except ValueError:
        return jsonify(error="invalid_limit"), 400
    

    limit = max(1, min(20, limit))

    if not q:
        return jsonify(error = "empty_query", results = []), 400
    

    tokens = re.findall(r"[a-z0-9]+", q.lower())

    if not tokens:
        return jsonify(error = "invalid_query", results = []), 400
    
    like = f"%{q.lower()}%"

    with get_conn() as conn:
        params = []

        code_clause = "LOWER(code) LIKE ?"
        params.append(f"%{q.lower()}%")

        desc_clauses = []
        for t in tokens:
            desc_clauses.append("LOWER(description) LIKE ?")
            params.append(f"%{t}%")

        desc_sql = " AND ".join(desc_clauses)

        where_sql = f"({code_clause}) OR ({desc_sql})"


        rows = conn.execute(
            f"""
            SELECT code, description, chapter, section, category, category_code
            FROM icd_codes
            WHERE {where_sql}
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()

    return jsonify(query=q, limit = limit, results = [dict(r) for r in rows])


@app.get("/icd/<code>")
def icd_get(code: str):
    code = code.strip()

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT code, description, chapter, section, category, category_code
            FROM icd_codes
            WHERE code = ?
            """,
            (code,),
        ).fetchone()

    if row is None:
        return jsonify(error="icd_code_not_found", code=code), 404
    
    return jsonify(dict(row))