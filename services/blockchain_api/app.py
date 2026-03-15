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


@app.get("/blockchain/events/<int:patient_id>")
def get_events(patient_id: int):
    try:
        w3, contract = get_contract()
    except ConnectionError as e:
        return jsonify(error="node_unreachable", detail=str(e)), 503

    admissions = contract.events.AdmissionRecorded.get_logs(
        from_block=0,
        argument_filters={"patientId": patient_id},
    )
    diagnoses = contract.events.DiagnosisRecorded.get_logs(
        from_block=0,
        argument_filters={"patientId": patient_id},
    )

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
    )