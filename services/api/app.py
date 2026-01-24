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
