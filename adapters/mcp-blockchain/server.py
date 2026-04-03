import logging
from collections import Counter
from datetime import datetime, timezone
import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
mcp = FastMCP("hl7-mcp-blockchain")

BLOCKCHAIN_API_BASE = "http://127.0.0.1:8001"
API_BASE = "http://127.0.0.1:8000"

_TOOL_COUNTS: dict[str, int] = {}

def _count(tool_name: str) -> None:
    _TOOL_COUNTS[tool_name] = _TOOL_COUNTS.get(tool_name, 0) + 1


@mcp.tool()
def blockchain_get_events(patient_id: int) -> dict:
    """Get all blockchain audit events (admissions and diagnoses) recorded for a patient."""
    _count("blockchain_get_events")
    r = httpx.get(
        f"{BLOCKCHAIN_API_BASE}/blockchain/events/{patient_id}",
        timeout=10.0,
    )
    try:
        data = r.json()
    except Exception:
        data = {"error": "bad_response", "status_code": r.status_code}
    if r.status_code >= 400:
        return {"ok": False, "status_code": r.status_code, "error": data}
    return {"ok": True, **data}


@mcp.tool()
def blockchain_get_all_events(limit: int = 50, offset: int = 0) -> dict:
    """Browse all blockchain audit events across all patients. Returns a paginated list of all admissions and diagnoses recorded on-chain, sorted by most recent first. Useful for auditing the entire chain."""
    _count("blockchain_get_all_events")
    limit = max(1, min(200, limit))
    offset = max(0, offset)
    r = httpx.get(
        f"{BLOCKCHAIN_API_BASE}/blockchain/events",
        params={"limit": limit, "offset": offset},
        timeout=15.0,
    )
    try:
        data = r.json()
    except Exception:
        data = {"error": "bad_response", "status_code": r.status_code}
    if r.status_code >= 400:
        return {"ok": False, "status_code": r.status_code, "error": data}
    return {"ok": True, **data}


@mcp.tool()
def blockchain_verify_patient(patient_id: int) -> dict:
    """Verify integrity of a patient's records by cross-checking the database against the blockchain audit trail. Returns matched records and any discrepancies — useful for detecting missing audit events or potential data tampering."""
    _count("blockchain_verify_patient")

    # Fetch patient from DB
    r_patient = httpx.get(f"{API_BASE}/patients/{patient_id}", timeout=5.0)
    if r_patient.status_code == 404:
        return {"ok": False, "error": "patient_not_found", "patient_id": patient_id}
    if r_patient.status_code >= 400:
        return {"ok": False, "error": "api_error", "detail": r_patient.text}

    # Fetch DB diagnoses
    r_diag = httpx.get(f"{API_BASE}/patients/{patient_id}/diagnoses", timeout=5.0)
    if r_diag.status_code >= 400:
        return {"ok": False, "error": "api_error", "detail": r_diag.text}
    db_diagnoses = r_diag.json().get("diagnoses", [])

    # Fetch blockchain events
    r_chain = httpx.get(f"{BLOCKCHAIN_API_BASE}/blockchain/events/{patient_id}", timeout=10.0)
    if r_chain.status_code >= 400:
        return {"ok": False, "error": "blockchain_api_error", "detail": r_chain.text}
    chain_data = r_chain.json()
    chain_diagnoses = chain_data.get("diagnoses", [])
    chain_admissions = chain_data.get("admissions", [])

    db_counts = Counter(d["icd_code"] for d in db_diagnoses)
    chain_counts = Counter(e["icdCode"] for e in chain_diagnoses)

    all_codes = db_counts.keys() | chain_counts.keys()
    discrepancies = []
    matched = 0

    for code in all_codes:
        db_n = db_counts[code]
        chain_n = chain_counts[code]
        if db_n == chain_n:
            matched += db_n
        elif db_n > chain_n:
            discrepancies.append({
                "type": "missing_from_blockchain",
                "icd_code": code,
                "db_count": db_n,
                "blockchain_count": chain_n,
                "detail": f"{db_n - chain_n} occurrence(s) in DB have no matching blockchain event",
            })
        else:
            discrepancies.append({
                "type": "blockchain_only",
                "icd_code": code,
                "db_count": db_n,
                "blockchain_count": chain_n,
                "detail": f"{chain_n - db_n} occurrence(s) on-chain have no matching DB record — possible data tampering",
            })

    verified = len(discrepancies) == 0

    return {
        "ok": True,
        "patient_id": patient_id,
        "verified": verified,
        "summary": {
            "db_diagnoses": len(db_diagnoses),
            "blockchain_diagnoses": len(chain_diagnoses),
            "blockchain_admissions": len(chain_admissions),
            "matched": matched,
            "missing_from_blockchain": sum(1 for d in discrepancies if d["type"] == "missing_from_blockchain"),
            "blockchain_only": sum(1 for d in discrepancies if d["type"] == "blockchain_only"),
        },
        "discrepancies": discrepancies,
    }


@mcp.tool()
def blockchain_audit_summary(patient_id: int) -> dict:
    """Get a chronological audit timeline of all blockchain events for a patient — admissions and diagnoses merged and sorted by timestamp. Reconstructed entirely from on-chain data."""
    _count("blockchain_audit_summary")

    r = httpx.get(f"{BLOCKCHAIN_API_BASE}/blockchain/events/{patient_id}", timeout=10.0)
    if r.status_code >= 400:
        return {"ok": False, "error": "blockchain_api_error", "detail": r.text}

    data = r.json()
    events = []

    for e in data.get("admissions", []):
        events.append({
            "timestamp_unix": e["timestamp"],
            "event_type": "admission",
            "detail": e["messageType"],
            "block": e["block"],
            "tx_hash": e["tx"],
        })

    for e in data.get("diagnoses", []):
        events.append({
            "timestamp_unix": e["timestamp"],
            "event_type": "diagnosis",
            "detail": f"ICD {e['icdCode']}",
            "block": e["block"],
            "tx_hash": e["tx"],
        })

    events.sort(key=lambda e: e["timestamp_unix"])

    timeline = [
        {
            "sequence": i + 1,
            "timestamp": datetime.fromtimestamp(e["timestamp_unix"], tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "event_type": e["event_type"],
            "detail": e["detail"],
            "block": e["block"],
            "tx_hash": e["tx_hash"],
        }
        for i, e in enumerate(events)
    ]

    return {
        "ok": True,
        "patient_id": patient_id,
        "total_events": len(timeline),
        "timeline": timeline,
    }


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
