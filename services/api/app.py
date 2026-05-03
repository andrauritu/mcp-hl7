import os
import re
import requests
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, jsonify, request, render_template, make_response, redirect, url_for

from db import init_db, get_db
from hl7_builder import build_adt_a03, build_adt_a04, build_rde_o11
from mllp_client import send as mllp_send, is_ack

BLOCKCHAIN_API_URL = os.environ.get("BLOCKCHAIN_API_URL", "http://127.0.0.1:8001")

app = Flask(__name__)
init_db()


@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.route("/")
def index():
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.get("/patients/full")
def list_patients_full():
    """Return patients with their diagnoses and prescriptions embedded — used by the dashboard."""
    limit_raw = request.args.get("limit", "100")
    try:
        limit = max(1, min(200, int(limit_raw)))
    except ValueError:
        return jsonify(error="invalid_limit"), 400

    with get_db() as conn:
        patients = [dict(r) for r in conn.execute(
            "SELECT id, name, dob, sex, created_at, discharged_at FROM patients ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()]

        for p in patients:
            p["diagnoses"] = [dict(r) for r in conn.execute(
                """SELECT d.icd_code, c.description, d.created_at
                   FROM diagnoses d JOIN icd_codes c ON c.code = d.icd_code
                   WHERE d.patient_id = ? ORDER BY d.created_at ASC""",
                (p["id"],),
            ).fetchall()]
            p["prescriptions"] = [dict(r) for r in conn.execute(
                """SELECT medication_name, atc_code, dose, unit, frequency, route, created_at
                   FROM prescriptions WHERE patient_id = ? ORDER BY created_at ASC""",
                (p["id"],),
            ).fetchall()]

    return jsonify(patients=patients, count=len(patients))


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
            expected = {"name": "string", "dob": "YYYY-MM-DD", "sex": "M|F|U"},
        ), 400
    
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO patients (name, dob, sex) VALUES (?, ?, ?)",
            (name, dob, sex),
        )

        patient_id = cur.lastrowid

        row = conn.execute(
            "SELECT id, name, dob, sex, created_at, discharged_at FROM patients WHERE id = ?",
            (patient_id,),
        ).fetchone()

    return jsonify(dict(row)), 201

@app.get('/patients')
def list_patients():
    limit_raw = request.args.get("limit", "50")
    try:
        limit = int(limit_raw)
    except ValueError:
        return jsonify(error="invalid_limit"), 400
    limit = max(1, min(200, limit))

    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, name, dob, sex, created_at, discharged_at FROM patients ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

    patients = [dict(r) for r in rows]
    return jsonify(patients=patients, count=len(patients))


@app.get('/patients/<int:patient_id>')
def get_patient(patient_id: int):
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, name, dob, sex, created_at, discharged_at FROM patients WHERE id = ?",
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

    with get_db() as conn:
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

    with get_db() as conn:
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


# ── ATC (medication) search ─────────────────────────────────────────────────────

@app.get("/atc/search")
def atc_search():
    q = str(request.args.get("q", "")).strip()
    limit_raw = request.args.get("limit") or "6"
    try:
        limit = int(limit_raw)
    except ValueError:
        return jsonify(error="invalid_limit"), 400
    limit = max(1, min(20, limit))

    if not q:
        return jsonify(error="empty_query", results=[]), 400

    tokens = re.findall(r"[a-z0-9]+", q.lower())
    if not tokens:
        return jsonify(error="invalid_query", results=[]), 400

    looks_like_code = bool(re.fullmatch(r"[a-z][0-9]{2}[a-z]{0,2}[0-9]{0,2}", q.lower()))

    with get_db() as conn:
        # Tier 1: code exact / prefix
        if looks_like_code:
            rows = conn.execute(
                """SELECT code, name, ddd, uom, adm_route
                   FROM atc_codes
                   WHERE code = ? OR code LIKE ?
                   ORDER BY CASE WHEN code = ? THEN 0 ELSE 1 END, code
                   LIMIT ?""",
                (q.upper(), f"{q.upper()}%", q.upper(), limit),
            ).fetchall()
            if rows:
                return jsonify(query=q, limit=limit, mode="code_exact",
                               tokens=tokens, results=[dict(r) for r in rows])

        # Tier 2: FTS5 + BM25
        fts_query = " ".join(tokens)
        rows = conn.execute(
            """SELECT c.code, c.name, c.ddd, c.uom, c.adm_route
               FROM atc_fts f
               JOIN atc_codes c ON c.code = f.code
               WHERE f.name MATCH ?
               ORDER BY bm25(atc_fts)
               LIMIT ?""",
            (fts_query, limit),
        ).fetchall()
        if rows:
            return jsonify(query=q, limit=limit, mode="fts",
                           tokens=tokens, results=[dict(r) for r in rows])

        # Tier 3: LIKE fallback
        clauses = []
        params = []
        for t in tokens:
            clauses.append("LOWER(name) LIKE ?")
            params.append(f"%{t}%")
        rows = conn.execute(
            f"""SELECT code, name, ddd, uom, adm_route
                FROM atc_codes
                WHERE {' AND '.join(clauses)}
                LIMIT ?""",
            (*params, limit),
        ).fetchall()

    return jsonify(query=q, limit=limit, mode="like",
                   tokens=tokens, results=[dict(r) for r in rows])


@app.get("/atc/<code>")
def atc_get(code: str):
    code = code.strip().upper()
    with get_db() as conn:
        row = conn.execute(
            "SELECT code, name, ddd, uom, adm_route FROM atc_codes WHERE code = ?",
            (code,),
        ).fetchone()
    if row is None:
        return jsonify(error="atc_code_not_found", code=code), 404
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

    with get_db() as conn:
        p = conn.execute(
            "SELECT id FROM patients WHERE id = ?",
            (patient_id,)
        ).fetchone()
        if p is None:
            return jsonify(error="patient_not_found", patient_id=patient_id), 404
        
    if icd_code:
        with get_db() as conn:
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

        blockchain_result = None
        try:
            bc = requests.post(
                f"{BLOCKCHAIN_API_URL}/blockchain/record_diagnosis",
                json={"patient_id": patient_id, "icd_code": icd_code},
                timeout=15.0,
            )
            blockchain_result = bc.json()
        except Exception as e:
            blockchain_result = {"ok": False, "error": str(e)}

        return jsonify(ok=True, diagnosis=dict(row), chosen={"code": icd["code"], "description": icd["description"]}, blockchain=blockchain_result)

    if not term:
        return jsonify(error = "missing_term_or_icd_code"), 400

    q_lower = term.lower()
    tokens = re.findall(r"[a-z0-9]+", q_lower)
    if not tokens:
        return jsonify(error = "empty_query"), 400

    with get_db() as conn:
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
    with get_db() as conn:
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


@app.post("/admissions")
def create_admission():
    """Build HL7 ADT^A04, send via MLLP, and record on blockchain — all in one atomic operation."""
    body = request.get_json(force=True) or {}
    patient_id = body.get("patient_id")

    if not isinstance(patient_id, int):
        return jsonify(error="invalid_patient_id"), 400

    with get_db() as conn:
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
        sex=patient["sex"],
        diagnoses=diagnoses,
    )

    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO hl7_messages (patient_id, message_type, hl7_text, status) VALUES (?, ?, ?, ?)",
            (patient_id, "ADT^A04", hl7_text, "built"),
        )
        conn.commit()
        message_id = cur.lastrowid

    def _send_hl7():
        try:
            ack_text = mllp_send(hl7_text)
            status = "ack" if is_ack(ack_text) else "nack"
            with get_db() as conn:
                conn.execute(
                    "UPDATE hl7_messages SET status = ?, ack_text = ? WHERE id = ?",
                    (status, ack_text, message_id),
                )
                conn.commit()
            return {"ok": True, "status": status, "ack_text": ack_text}
        except ConnectionError as e:
            with get_db() as conn:
                conn.execute(
                    "UPDATE hl7_messages SET status = ? WHERE id = ?",
                    ("failed", message_id),
                )
                conn.commit()
            return {"ok": False, "error": "receiver_unreachable", "detail": str(e)}

    def _record_blockchain():
        try:
            r = requests.post(
                f"{BLOCKCHAIN_API_URL}/blockchain/record_admission",
                json={"patient_id": patient_id, "message_type": "ADT^A04"},
                timeout=15.0,
            )
            return r.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    with ThreadPoolExecutor(max_workers=2) as executor:
        hl7_future = executor.submit(_send_hl7)
        blockchain_future = executor.submit(_record_blockchain)
        hl7_result = hl7_future.result()
        blockchain_result = blockchain_future.result()

    return jsonify(
        ok=True,
        message_id=message_id,
        patient_id=patient_id,
        hl7=hl7_result,
        blockchain=blockchain_result,
    ), 201


@app.post("/hl7/build/adt_a04")
def  hl7_build_adt_a04():
    body = request.get_json(force=True) or {}
    patient_id = body.get("patient_id")

    if not isinstance(patient_id, int):
        return jsonify(error="invalid_patient_id"), 400
    
    with get_db() as conn:
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

    with get_db() as conn:
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
    
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, patient_id, hl7_text, status from hl7_messages WHERE id = ?",
            (message_id,),
        ).fetchone()

    if row is None:
        return jsonify(error = "message_not_found", message_id = message_id), 404

    if row["status"] not in ("built", "failed", "nack"):
        return jsonify(
            error="message_already_sent",
            message_id=message_id,
            status=row["status"],
        ), 409

    try:
        ack_text = mllp_send(row["hl7_text"])
    except ConnectionError as e:
        return jsonify(error = "receiver_unreachable", detail=str(e)), 503

    status = "ack" if is_ack(ack_text) else "nack"

    with get_db() as conn:
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


@app.post("/patients/<int:patient_id>/prescriptions")
def create_prescription(patient_id: int):
    """Create a prescription, build HL7 RDE^O11, send via MLLP, and record on blockchain."""
    body = request.get_json(force=True) or {}

    medication_name = (body.get("medication_name") or "").strip()
    atc_code = (body.get("atc_code") or "").strip().upper() or None
    dose = (body.get("dose") or "").strip()
    unit = (body.get("unit") or "").strip()
    frequency = (body.get("frequency") or "").strip()
    route = (body.get("route") or "oral").strip()
    prescriber = (body.get("prescriber") or "Dr. MCP").strip()
    icd_code = (body.get("icd_code") or "").strip().upper() or None

    if not medication_name or not dose or not unit or not frequency:
        return jsonify(
            error="invalid_input",
            expected={"medication_name": "string", "dose": "string", "unit": "string", "frequency": "string"},
        ), 400

    with get_db() as conn:
        patient = conn.execute(
            "SELECT id, name, dob, sex FROM patients WHERE id = ?",
            (patient_id,),
        ).fetchone()
        if patient is None:
            return jsonify(error="patient_not_found", patient_id=patient_id), 404

    icd_description = None
    if icd_code:
        with get_db() as conn:
            icd_row = conn.execute(
                "SELECT code, description FROM icd_codes WHERE code = ?",
                (icd_code,),
            ).fetchone()
            if icd_row:
                icd_description = icd_row["description"]

    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO prescriptions
               (patient_id, medication_name, atc_code, dose, unit, frequency, route, prescriber, icd_code)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (patient_id, medication_name, atc_code, dose, unit, frequency, route, prescriber, icd_code),
        )
        conn.commit()
        rx_id = cur.lastrowid

    hl7_text = build_rde_o11(
        patient_id=patient["id"],
        patient_name=patient["name"],
        dob=patient["dob"],
        sex=patient["sex"],
        medication_name=medication_name,
        atc_code=atc_code,
        dose=dose,
        unit=unit,
        frequency=frequency,
        route=route,
        prescriber=prescriber,
        icd_code=icd_code,
        icd_description=icd_description,
    )

    with get_db() as conn:
        cur2 = conn.execute(
            "INSERT INTO hl7_messages (patient_id, message_type, hl7_text, status) VALUES (?, ?, ?, ?)",
            (patient_id, "RDE^O11", hl7_text, "built"),
        )
        conn.commit()
        message_id = cur2.lastrowid

    def _send_hl7():
        try:
            ack_text = mllp_send(hl7_text)
            status = "ack" if is_ack(ack_text) else "nack"
            with get_db() as conn:
                conn.execute(
                    "UPDATE hl7_messages SET status = ?, ack_text = ? WHERE id = ?",
                    (status, ack_text, message_id),
                )
                conn.commit()
            return {"ok": True, "status": status, "ack_text": ack_text}
        except ConnectionError as e:
            with get_db() as conn:
                conn.execute(
                    "UPDATE hl7_messages SET status = ? WHERE id = ?",
                    ("failed", message_id),
                )
                conn.commit()
            return {"ok": False, "error": "receiver_unreachable", "detail": str(e)}

    def _record_blockchain():
        try:
            r = requests.post(
                f"{BLOCKCHAIN_API_URL}/blockchain/record_prescription",
                json={
                    "patient_id": patient_id,
                    "medication": medication_name,
                    "icd_code": icd_code or "",
                },
                timeout=15.0,
            )
            return r.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    with ThreadPoolExecutor(max_workers=2) as executor:
        hl7_future = executor.submit(_send_hl7)
        blockchain_future = executor.submit(_record_blockchain)
        hl7_result = hl7_future.result()
        blockchain_result = blockchain_future.result()

    return jsonify(
        ok=True,
        prescription_id=rx_id,
        message_id=message_id,
        patient_id=patient_id,
        medication=medication_name,
        hl7=hl7_result,
        blockchain=blockchain_result,
    ), 201


@app.get("/patients/<int:patient_id>/prescriptions")
def list_prescriptions(patient_id: int):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, patient_id, medication_name, atc_code, dose, unit, frequency,
                      route, prescriber, icd_code, created_at
               FROM prescriptions
               WHERE patient_id = ?
               ORDER BY created_at DESC""",
            (patient_id,),
        ).fetchall()
    return jsonify(patient_id=patient_id, prescriptions=[dict(r) for r in rows])


@app.post("/patients/<int:patient_id>/discharge")
def discharge_patient(patient_id: int):
    """Set discharged_at, build HL7 ADT^A03, send via MLLP, and record on blockchain."""
    with get_db() as conn:
        patient = conn.execute(
            "SELECT id, name, dob, sex, discharged_at FROM patients WHERE id = ?",
            (patient_id,),
        ).fetchone()

        if patient is None:
            return jsonify(error="patient_not_found", patient_id=patient_id), 404

        if patient["discharged_at"] is not None:
            return jsonify(error="already_discharged", discharged_at=patient["discharged_at"]), 409

        conn.execute(
            "UPDATE patients SET discharged_at = datetime('now') WHERE id = ?",
            (patient_id,),
        )
        conn.commit()

        updated = conn.execute(
            "SELECT id, name, dob, sex, created_at, discharged_at FROM patients WHERE id = ?",
            (patient_id,),
        ).fetchone()

    patient_dict = dict(updated)

    hl7_text = build_adt_a03(
        patient_id=patient["id"],
        patient_name=patient["name"],
        dob=patient["dob"],
        sex=patient["sex"],
    )

    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO hl7_messages (patient_id, message_type, hl7_text, status) VALUES (?, ?, ?, ?)",
            (patient_id, "ADT^A03", hl7_text, "built"),
        )
        conn.commit()
        message_id = cur.lastrowid

    def _send_hl7():
        try:
            ack_text = mllp_send(hl7_text)
            status = "ack" if is_ack(ack_text) else "nack"
            with get_db() as conn:
                conn.execute(
                    "UPDATE hl7_messages SET status = ?, ack_text = ? WHERE id = ?",
                    (status, ack_text, message_id),
                )
                conn.commit()
            return {"ok": True, "status": status, "ack_text": ack_text}
        except ConnectionError as e:
            with get_db() as conn:
                conn.execute(
                    "UPDATE hl7_messages SET status = ? WHERE id = ?",
                    ("failed", message_id),
                )
                conn.commit()
            return {"ok": False, "error": "receiver_unreachable", "detail": str(e)}

    def _record_blockchain():
        try:
            r = requests.post(
                f"{BLOCKCHAIN_API_URL}/blockchain/record_discharge",
                json={"patient_id": patient_id, "message_type": "ADT^A03"},
                timeout=15.0,
            )
            return r.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    with ThreadPoolExecutor(max_workers=2) as executor:
        hl7_future = executor.submit(_send_hl7)
        blockchain_future = executor.submit(_record_blockchain)
        hl7_result = hl7_future.result()
        blockchain_result = blockchain_future.result()

    return jsonify(
        ok=True,
        patient=patient_dict,
        message_id=message_id,
        hl7=hl7_result,
        blockchain=blockchain_result,
    ), 200

