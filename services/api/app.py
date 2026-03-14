import re
from flask import Flask, jsonify, request

from db import init_db, get_conn
from hl7_builder import build_adt_a04

from mllp_client import send as mllp_send, is_ack

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
    
    looks_like_code = bool(re.fullmatch(r"[a-z][0-9]{2}(\.[0-9a-z]+)?", q.lower()))

    with get_conn() as conn:
        if looks_like_code:
            rows = conn.execute(
                """
                SELECT code, description, chapter, section, category, category_code
                FROM icd_codes
                WHERE code = ?
                    OR code LIKE ?
                ORDER BY
                    CASE WHEN code = ? THEN 0 ELSE 1 END,
                    code
                LIMIT ?
                """,
                (q.upper(), f"{q.upper()}%", q.upper(), limit),
            ).fetchall()

            if rows:
                return jsonify(
                    query=q,
                    limit=limit,
                    mode = "code_exact",
                    tokens = tokens,
                    results = [dict(r) for r in rows],
                )
            
        fts_query = " ".join(tokens)
        rows = conn.execute(
            """
            SELECT c.code, c.description, c.chapter, c.section, c.category, c.category_code
            FROM icd_fts f
            JOIN icd_codes c ON c.code = f.code
            WHERE f.description MATCH ?
            ORDER BY bm25(icd_fts)
            LIMIT ?
            """,
            (fts_query, limit),
        ).fetchall()

        if rows:
            return jsonify(
                query=q,
                limit=limit,
                mode = "fts",
                tokens = tokens,
                results = [dict(r) for r in rows],
            )
        
        desc_clauses = []
        params = []
        for t in tokens:
            desc_clauses.append("LOWER(description) LIKE ?")
            params.append(f"%{t}%")

        desc_sql = " AND ".join(desc_clauses)

        rows = conn.execute(
            f"""
            SELECT code, description, chapter, section, category, category_code
            FROM icd_codes
            WHERE {desc_sql}
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()

    return jsonify(
        query=q,
        limit=limit,
        mode = "like",
        tokens = tokens,
        results = [dict(r) for r in rows],
    )

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


@app.post("/patients/<int:patient_id>/diagnoses")
def add_diagnosis(patient_id: int):
    body = request.get_json(force=True) or {}
    term = (body.get("term") or "").strip()
    icd_code = (body.get("icd_code") or "").strip().upper()
    limit = body.get("limit", 5)

    try:
        limit = int(limit)
    except ValueError:
        return jsonify(error="invalid_limit"), 400
    limit = max(1, min(20, limit))

    with get_conn() as conn:
        p = conn.execute(
            "SELECT id FROM patients WHERE id = ?",
            (patient_id,)
        ).fetchone()
        if p is None:
            return jsonify(error="patient_not_found", patient_id=patient_id), 404
        
    if icd_code:
        with get_conn() as conn:
            icd = conn.execute(
                "SELECT code, description FROM icd_codes WHERE code = ?",
                (icd_code,),

            ).fetchone()
            if icd is None:
                return jsonify(error="icd_code_not_found", icd_code=icd_code), 404

            cur = conn.execute(
                "INSERT INTO diagnoses (patient_id, icd_code, term) VALUES (?, ?, ?)",
                (patient_id, icd_code, term or None),
            )

            conn.commit()

            diag_id = cur.lastrowid
            row = conn.execute(
                """
                SELECT d.id, d.patient_id, d.icd_code, d.term, d.created_at, c.description
                FROM diagnoses d
                JOIN icd_codes c ON c.code = d.icd_code
                WHERE d.id = ?
                """,
                (diag_id,),
            ).fetchone()

        return jsonify(ok = True, diagnosis = dict(row), chosen = {"code": icd["code"], "description": icd["description"]})

    if not term:
        return jsonify(error = "missing_term_or_icd_code"), 400

    q_lower = term.lower()
    tokens = re.findall(r"[a-z0-9]+", q_lower)
    if not tokens:
        return jsonify(error = "empty_query"), 400

    with get_conn() as conn:
        candidates = []
        try:
            fts_query = " ".join(tokens)
            rows = conn.execute(
                """
                SELECT c.code, c.description
                FROM icd_fts f
                JOIN icd_codes c ON c.code = f.code
                WHERE f.description MATCH ?
                ORDER BY bm25(icd_fts)
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
            candidates = [dict(r) for r in rows]

        except Exception:
            candidates = []

        if not candidates:
            desc_clauses = []
            params = []
            for t in tokens:
                desc_clauses.append("LOWER(description) LIKE ?")
                params.append(f"%{t}%")

            desc_sql = " AND ".join(desc_clauses)

            rows = conn.execute(
                f"""
                SELECT code, description
                FROM icd_codes
                WHERE {desc_sql}
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
            candidates = [dict(r) for r in rows]

    if not candidates:
        return jsonify(ok = False, status = "no_match", term = term, candidates = []), 200

    return jsonify(ok = True, status = "needs_selection", term = term, candidates = candidates), 200


@app.get("/patients/<int:patient_id>/diagnoses")
def list_diagnoses(patient_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT d.id, d.patient_id, d.icd_code, d.term, d.created_at, c.description
            FROM diagnoses d
            JOIN icd_codes c ON c.code = d.icd_code
            WHERE d.patient_id = ?
            ORDER BY d.created_at DESC
            """,
            (patient_id,),
        ).fetchall()
    return jsonify(patient_id=patient_id, diagnoses=[dict(r) for r in rows])


@app.post("/hl7/build/adt_a04")
def  hl7_build_adt_a04():
    body = request.get_json(force=True) or {}
    patient_id = body.get("patient_id")

    if not isinstance(patient_id, int):
        return jsonify(error="invalid_patient_id"), 400
    
    with get_conn() as conn:
        patient = conn.execute(
            "SELECT id, name, dob, sex FROM patients WHERE id = ?",
            (patient_id,),
        ).fetchone()

        if patient is None:
            return jsonify(error="patient_not_found", patient_id=patient_id), 404
        
        dx_rows = conn.execute(
            """
            SELECT d.icd_code, c.description
            FROM diagnoses d
            JOIN icd_codes c ON c.code = d.icd_code
            WHERE d.patient_id = ?
            ORDER BY d.created_at ASC
            """,
            (patient_id,),
        ).fetchall()

    diagnoses = [dict(r) for r in dx_rows]

    hl7_text = build_adt_a04(
        patient_id=patient["id"],
        patient_name=patient["name"],
        dob=patient["dob"],
        sex = patient["sex"],
        diagnoses=diagnoses,
    )

    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO hl7_messages (patient_id, message_type, hl7_text, status) VALUES (?, ?, ?, ?)",
            (patient_id, "ADT^A04", hl7_text, "built"),
        )
        conn.commit()
        message_id = cur.lastrowid

    return jsonify(
        ok = True,
        message_id = message_id,
        patient_id = patient_id,
        message_type = "ADT^A04",
        diagnosis_count = len(diagnoses),
        hl7_text = hl7_text,
    ), 201

  
@app.post("/hl7/send")
def hl7_send():
    """Send a built HL7 message to the mock receiver via MLLP. Returns ACK or NACK status and stores the result in the database."""
    body = request.get_json(force = True) or {}
    message_id = body.get("message_id")

    if not isinstance(message_id, int):
        return jsonify(error = "missing_message_id"), 400
    
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, patient_id, hl7_text, status from hl7_messages WHERE id = ?",
            (message_id,),
        ).fetchone()

    if row is None:
        return jsonify(error = "message_not_found", message_id = message_id), 404

    if row["status"] not in ("built", "failed"):
        return jsonify(error = "message_not_found", message_id = message_id), 404

    if row["status"] not in ("built", "nack"):
        return jsonify(
            error = "message_already_sent", 
            message_id = message_id,
            status = row["status"],
        ), 409

    try:
        ack_text = mllp_send(row["hl7_text"])
    except ConnectionError as e:
        return jsonify(error = "receiver_unreachable", detail=str(e)), 503

    status = "ack" if is_ack(ack_text) else "nack"

    with get_conn() as conn:
        conn.execute(
            "UPDATE hl7_messages SET status = ?, ack_text = ? WHERE id = ?",
            (status, ack_text, message_id),
        )
        conn.commit()

    return jsonify(
        ok = True,
        message_id = message_id,
        status = status,
        ack_text = ack_text
    )

