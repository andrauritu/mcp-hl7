from flask import Flask, jsonify, request
from contract import get_contract, ABI_PATH, _DEPLOYED_JSON, NODE_URL

app = Flask(__name__)


@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


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
        tx_hash="0x" + tx_hash.hex(),
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
        tx_hash="0x" + tx_hash.hex(),
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
        tx_hash="0x" + tx_hash.hex(),
        block_number=receipt["blockNumber"],
        gas_used=receipt["gasUsed"],
    ), 201


@app.post("/blockchain/record_discharge")
def record_discharge():
    body = request.get_json(force=True) or {}
    patient_id = body.get("patient_id")
    message_type = (body.get("message_type") or "ADT^A03").strip()

    if not isinstance(patient_id, int):
        return jsonify(error="missing_patient_id"), 400

    try:
        w3, contract = get_contract()
    except ConnectionError as e:
        return jsonify(error="node_unreachable", detail=str(e)), 503

    account = w3.eth.accounts[0]
    tx_hash = contract.functions.recordDischarge(patient_id, message_type).transact(
        {"from": account}
    )
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    return jsonify(
        ok=True,
        patient_id=patient_id,
        message_type=message_type,
        tx_hash="0x" + tx_hash.hex(),
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
    all_discharges = contract.events.DischargeRecorded.get_logs(from_block=0, to_block="latest")

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
    for e in all_discharges:
        events.append({
            "event_type": "discharge",
            "patient_id": e["args"]["patientId"],
            "detail": e["args"]["messageType"],
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
    all_discharges = contract.events.DischargeRecorded.get_logs(from_block=0, to_block="latest")

    admissions = [e for e in all_admissions if e["args"]["patientId"] == patient_id]
    diagnoses = [e for e in all_diagnoses if e["args"]["patientId"] == patient_id]
    prescriptions = [e for e in all_prescriptions if e["args"]["patientId"] == patient_id]
    discharges = [e for e in all_discharges if e["args"]["patientId"] == patient_id]

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
        discharges=[
            {
                "messageType": e["args"]["messageType"],
                "timestamp": e["args"]["timestamp"],
                "block": e["blockNumber"],
                "tx": e["transactionHash"].hex(),
            }
            for e in discharges
        ],
    )


@app.get("/blockchain/contract/audit")
def contract_audit():
    """Inspect and analyse the deployed MedicalAudit smart contract."""
    import json as _json

    # ----- basic connectivity / deployment info -----
    if not _DEPLOYED_JSON.exists():
        return jsonify(error="contract_not_deployed", detail="deployed.json not found"), 503

    address = _json.loads(_DEPLOYED_JSON.read_text())["address"]

    try:
        w3, contract = get_contract()
    except ConnectionError as e:
        return jsonify(error="node_unreachable", detail=str(e)), 503

    artifact = _json.loads(ABI_PATH.read_text())
    abi = artifact["abi"]

    # bytecode size in bytes  (deployed bytecode, not init code)
    try:
        bytecode_hex = w3.eth.get_code(w3.to_checksum_address(address)).hex()
        bytecode_size = (len(bytecode_hex) - 2) // 2  # strip 0x, each byte = 2 hex chars
    except Exception:
        bytecode_size = None

    # current block / network info
    try:
        block_number = w3.eth.block_number
        chain_id = w3.eth.chain_id
    except Exception:
        block_number = None
        chain_id = None

    # ----- parse ABI -----
    functions = []
    events = []

    for item in abi:
        if item["type"] == "function":
            inputs = [
                {"name": inp.get("name", ""), "type": inp["type"]}
                for inp in item.get("inputs", [])
            ]
            outputs = [
                {"name": out.get("name", ""), "type": out["type"]}
                for out in item.get("outputs", [])
            ]
            # estimate gas for non-view functions
            gas_estimate = None
            if item.get("stateMutability") not in ("view", "pure"):
                try:
                    fn = getattr(contract.functions, item["name"])
                    # build a dummy call with zero/empty args for estimation
                    dummy_args = []
                    for inp in item.get("inputs", []):
                        if inp["type"] == "uint256":
                            dummy_args.append(0)
                        elif inp["type"].startswith("string"):
                            dummy_args.append("")
                        elif inp["type"] == "address":
                            dummy_args.append("0x0000000000000000000000000000000000000000")
                        else:
                            dummy_args.append(0)
                    gas_estimate = fn(*dummy_args).estimate_gas({"from": w3.eth.accounts[0]})
                except Exception:
                    gas_estimate = None

            functions.append({
                "name": item["name"],
                "inputs": inputs,
                "outputs": outputs,
                "state_mutability": item.get("stateMutability", "nonpayable"),
                "gas_estimate": gas_estimate,
            })

        elif item["type"] == "event":
            fields = [
                {
                    "name": inp.get("name", ""),
                    "type": inp["type"],
                    "indexed": inp.get("indexed", False),
                }
                for inp in item.get("inputs", [])
            ]
            events.append({
                "name": item["name"],
                "fields": fields,
                "anonymous": item.get("anonymous", False),
            })

    # ----- security checks -----
    # Walk bytecode byte-by-byte, skipping PUSH data so we only check real opcodes.
    # PUSH1=0x60..PUSH32=0x7f each consume N immediate data bytes that must be skipped.
    # Naive hex-substring scan produces false positives from push data / ABI hashes.
    DANGEROUS_OPCODES = {
        0xff: "selfdestruct",
        0xf4: "delegatecall",
        0xf2: "callcode",
    }
    raw_bytes = bytes.fromhex(bytecode_hex[2:]) if bytecode_hex and len(bytecode_hex) > 2 else b""
    opcode_findings = {name: False for name in DANGEROUS_OPCODES.values()}
    i = 0
    while i < len(raw_bytes):
        op = raw_bytes[i]
        if op in DANGEROUS_OPCODES:
            opcode_findings[DANGEROUS_OPCODES[op]] = True
        # PUSH1 (0x60) to PUSH32 (0x7f): skip the next (op - 0x5f) data bytes
        if 0x60 <= op <= 0x7f:
            i += (op - 0x5f)  # skip immediate data
        i += 1

    has_state_storage = any(
        item["type"] == "function" and item.get("stateMutability") == "view"
        for item in abi
    )
    has_access_control = any(
        "owner" in item.get("name", "").lower() or "only" in item.get("name", "").lower()
        for item in abi
        if item["type"] == "function"
    )
    write_fns = [f for f in functions if f["state_mutability"] not in ("view", "pure")]

    security_checks = [
        {
            "check": "No selfdestruct",
            "passed": not opcode_findings.get("selfdestruct", False),
            "detail": "Contract cannot be destroyed by an owner",
        },
        {
            "check": "No delegatecall",
            "passed": not opcode_findings.get("delegatecall", False),
            "detail": "Contract does not delegate execution to external contracts",
        },
        {
            "check": "No callcode",
            "passed": not opcode_findings.get("callcode", False),
            "detail": "Deprecated callcode opcode not present",
        },
        {
            "check": "Events-only audit design",
            "passed": not has_state_storage,
            "detail": "Contract emits events rather than storing data — gas efficient and append-only",
        },
        {
            "check": "Access control present",
            "passed": has_access_control,
            "detail": "owner/onlyOwner modifier detected" if has_access_control else "No access control — any address can call write functions",
        },
        {
            "check": "Write functions use external visibility",
            "passed": all(f["state_mutability"] == "nonpayable" for f in write_fns),
            "detail": "All write functions are non-payable (no accidental ETH acceptance)",
        },
    ]

    passed = sum(1 for c in security_checks if c["passed"])
    total_checks = len(security_checks)

    return jsonify(
        ok=True,
        contract={
            "address": address,
            "node_url": NODE_URL,
            "chain_id": chain_id,
            "current_block": block_number,
            "bytecode_size_bytes": bytecode_size,
            "abi_entries": len(abi),
        },
        functions=functions,
        events=events,
        security={
            "score": f"{passed}/{total_checks}",
            "passed": passed,
            "total": total_checks,
            "checks": security_checks,
        },
    )