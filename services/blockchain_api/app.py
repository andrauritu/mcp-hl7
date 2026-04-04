from flask import Flask, jsonify, request
from contract import get_contract

app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.post("/blockchain/record_admission")
def record_admission():
    body = request.get_json(force=True) or {}
    patient_id = body.get("patient_id")
    message_type = (body.get("message_type") or "ADT^A04").strip()

    if not isinstance(patient_id, int):
        return jsonify(error="missing_patient_id"), 400

    try:
        w3, contract = get_contract()
    except ConnectionError as e:
        return jsonify(error="node_unreachable", detail=str(e)), 503

    account = w3.eth.accounts[0]
    tx_hash = contract.functions.recordAdmission(patient_id, message_type).transact(
        {"from": account}
    )
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    return jsonify(
        ok=True,
        patient_id=patient_id,
        message_type=message_type,
        tx_hash=tx_hash.hex(),
        block_number=receipt["blockNumber"],
        gas_used=receipt["gasUsed"],
    ), 201


@app.post("/blockchain/record_diagnosis")
def record_diagnosis():
    body = request.get_json(force=True) or {}
    patient_id = body.get("patient_id")
    icd_code = (body.get("icd_code") or "").strip()

    if not isinstance(patient_id, int) or not icd_code:
        return jsonify(error="missing_patient_id_or_icd_code"), 400

    try:
        w3, contract = get_contract()
    except ConnectionError as e:
        return jsonify(error="node_unreachable", detail=str(e)), 503

    account = w3.eth.accounts[0]
    tx_hash = contract.functions.recordDiagnosis(patient_id, icd_code).transact(
        {"from": account}
    )
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    return jsonify(
        ok=True,
        patient_id=patient_id,
        icd_code=icd_code,
        tx_hash=tx_hash.hex(),
        block_number=receipt["blockNumber"],
        gas_used=receipt["gasUsed"],
    ), 201


@app.post("/blockchain/record_prescription")
def record_prescription():
    body = request.get_json(force=True) or {}
    patient_id = body.get("patient_id")
    medication = (body.get("medication") or "").strip()
    icd_code = (body.get("icd_code") or "").strip()

    if not isinstance(patient_id, int) or not medication:
        return jsonify(error="missing_patient_id_or_medication"), 400

    try:
        w3, contract = get_contract()
    except ConnectionError as e:
        return jsonify(error="node_unreachable", detail=str(e)), 503

    account = w3.eth.accounts[0]
    tx_hash = contract.functions.recordPrescription(patient_id, medication, icd_code).transact(
        {"from": account}
    )
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    return jsonify(
        ok=True,
        patient_id=patient_id,
        medication=medication,
        icd_code=icd_code,
        tx_hash=tx_hash.hex(),
        block_number=receipt["blockNumber"],
        gas_used=receipt["gasUsed"],
    ), 201


@app.get("/blockchain/events")
def get_all_events():
    try:
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
    except ValueError:
        return jsonify(error="invalid_limit_or_offset"), 400
    limit = max(1, min(200, limit))
    offset = max(0, offset)

    try:
        w3, contract = get_contract()
    except ConnectionError as e:
        return jsonify(error="node_unreachable", detail=str(e)), 503

    all_admissions = contract.events.AdmissionRecorded.get_logs(from_block=0, to_block="latest")
    all_diagnoses = contract.events.DiagnosisRecorded.get_logs(from_block=0, to_block="latest")
    all_prescriptions = contract.events.PrescriptionRecorded.get_logs(from_block=0, to_block="latest")

    events = []
    for e in all_admissions:
        events.append({
            "event_type": "admission",
            "patient_id": e["args"]["patientId"],
            "detail": e["args"]["messageType"],
            "timestamp": e["args"]["timestamp"],
            "block": e["blockNumber"],
            "tx": e["transactionHash"].hex(),
        })
    for e in all_diagnoses:
        events.append({
            "event_type": "diagnosis",
            "patient_id": e["args"]["patientId"],
            "detail": e["args"]["icdCode"],
            "timestamp": e["args"]["timestamp"],
            "block": e["blockNumber"],
            "tx": e["transactionHash"].hex(),
        })
    for e in all_prescriptions:
        events.append({
            "event_type": "prescription",
            "patient_id": e["args"]["patientId"],
            "detail": f"{e['args']['medication']}" + (f" ({e['args']['icdCode']})" if e["args"]["icdCode"] else ""),
            "timestamp": e["args"]["timestamp"],
            "block": e["blockNumber"],
            "tx": e["transactionHash"].hex(),
        })

    events.sort(key=lambda ev: ev["block"], reverse=True)
    total = len(events)
    page = events[offset:offset + limit]

    return jsonify(
        ok=True,
        total=total,
        limit=limit,
        offset=offset,
        events=page,
    )


@app.get("/blockchain/events/<int:patient_id>")
def get_events(patient_id: int):
    try:
        w3, contract = get_contract()
    except ConnectionError as e:
        return jsonify(error="node_unreachable", detail=str(e)), 503

    all_admissions = contract.events.AdmissionRecorded.get_logs(from_block=0, to_block="latest")
    all_diagnoses = contract.events.DiagnosisRecorded.get_logs(from_block=0, to_block="latest")
    all_prescriptions = contract.events.PrescriptionRecorded.get_logs(from_block=0, to_block="latest")

    admissions = [e for e in all_admissions if e["args"]["patientId"] == patient_id]
    diagnoses = [e for e in all_diagnoses if e["args"]["patientId"] == patient_id]
    prescriptions = [e for e in all_prescriptions if e["args"]["patientId"] == patient_id]

    return jsonify(
        ok=True,
        patient_id=patient_id,
        admissions=[
            {
                "messageType": e["args"]["messageType"],
                "timestamp": e["args"]["timestamp"],
                "block": e["blockNumber"],
                "tx": e["transactionHash"].hex(),
            }
            for e in admissions
        ],
        diagnoses=[
            {
                "icdCode": e["args"]["icdCode"],
                "timestamp": e["args"]["timestamp"],
                "block": e["blockNumber"],
                "tx": e["transactionHash"].hex(),
            }
            for e in diagnoses
        ],
        prescriptions=[
            {
                "medication": e["args"]["medication"],
                "icdCode": e["args"]["icdCode"],
                "timestamp": e["args"]["timestamp"],
                "block": e["blockNumber"],
                "tx": e["transactionHash"].hex(),
            }
            for e in prescriptions
        ],
    )