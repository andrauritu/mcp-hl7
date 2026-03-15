import logging
import sys
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import PromptMessage, TextContent

logging.basicConfig(level=logging.INFO)
mcp = FastMCP("hl7-mcp")

API_BASE = "http://127.0.0.1:8000"
BLOCKCHAIN_API_BASE = "http://127.0.0.1:8001"

@mcp.tool()
def ping() -> str:
    """Check if the API is reachable. Returns ok if healthy."""
    try:
        r = httpx.get(f"{API_BASE}/health", timeout=3.0)
        r.raise_for_status()
        data = r.json()
        return f"ok from api: {data.get('status')}"
    except Exception as e:
        print(f"[ping] error calling API: {e}", file=sys.stderr)
        return "error: api unreachable"

@mcp.tool()
def patient_create(name: str, dob: str, sex: str) -> dict:
    """Create a new patient. dob is YYYY-MM-DD. sex is M, F, or U."""
    r = httpx.post(
        f"{API_BASE}/patients",
        json={"name": name, "dob": dob, "sex": sex},
        timeout=5.0,
    )

    try:
        data = r.json()
    except Exception:
        data = {"error": "bad_response", "status_code": r.status_code}

    if r.status_code >= 400:
        return {"ok": False, "status_code": r.status_code, "error": data} 
    
    return {"ok": True, "patient": data}


@mcp.tool()
def patient_get(patient_id: int) -> dict:
    """Get a patient record by their numeric ID."""
    r = httpx.get(f"{API_BASE}/patients/{patient_id}", timeout=5.0)
    
    try:
        data = r.json()
    except Exception:
        data = {"error": "bad_response", "status_code": r.status_code}

    if r.status_code >= 400:
        return {"ok": False, "status_code": r.status_code, "error": data} 
    
    return {"ok": True, "patient": data}


@mcp.tool()
def icd_search(q: str, limit: int = 5) -> dict:
    """Search ICD-10 codes by medical term or description. Returns ranked results."""
    if limit < 1:
        limit = 1
    if limit > 20:
        limit = 20

    r = httpx.get(
        f"{API_BASE}/icd/search",
        params={"q": q, "limit": limit},
        timeout=5.0,
    )

    try:
        data = r.json()
    except Exception:
        data = {"error": "bad_response", "status_code": r.status_code}
    
    if r.status_code >= 400:
        return {"ok": False, "status_code": r.status_code, "error": data}

    return {"ok": True, **data}


@mcp.tool()
def icd_get(code: str) -> dict:
    """Get a single ICD-10 code record by exact code, e.g. A15.0."""
    code = code.strip()
    if not code:
        return {"ok": False, "status_code": 400, "error": "empty_code"}

    r = httpx.get(f"{API_BASE}/icd/{code}", timeout=5.0)

    try:
        data = r.json()
    except Exception:
        data = {"error": "bad_response", "status_code": r.status_code}

    if r.status_code >= 400:
        return {"ok": False, "status_code": r.status_code, "error": data}
    
    return {"ok": True, "icd": data}


_TOOL_COUNTS: dict[str, int] = {}
def _count(tool_name: str) -> None:
    _TOOL_COUNTS[tool_name] = _TOOL_COUNTS.get(tool_name, 0) + 1

@mcp.tool()
def get_usage_stats() -> dict:
    """Return how many times each MCP tool has been called in this session."""
    _count("get_usage_stats")
    return {"ok": True, "counts": dict(_TOOL_COUNTS)}


@mcp.tool()
def patient_add_diagnosis(patient_id: int, term: str, auto_select: bool = True, limit: int = 5) -> dict:
    """Search ICD-10 for term and add the top match as a diagnosis for the patient. If auto_select is False, returns candidates for manual selection."""
    _count("patient_add_diagnosis")

    r = httpx.post(
        f"{API_BASE}/patients/{patient_id}/diagnoses",
        json={"term": term, "limit": limit},
        timeout=10.0,
    )
    data = r.json()

    if r.status_code >= 400:
        return {"ok": False, "status_code": r.status_code, "error": data}
    
    candidates = data.get("candidates") or []
    if data.get("status") == "needs_selection":
        if not candidates:
            return {"ok": False, "status": "no_match", "term": term, "candidates": []}
        
        if not auto_select:
            return {"ok": True, "status": "needs_selection", "term": term, "candidates": candidates}
        
        chosen = candidates[0]
        chosen_code = chosen["code"]

        r2 = httpx.post(
            f"{API_BASE}/patients/{patient_id}/diagnoses",
            json={"term": term, "icd_code": chosen_code},
            timeout=10.0,
        )

        data2 = r2.json()
        if r2.status_code >= 400:
            return {"ok": False, "status_code": r2.status_code, "error": data2}
        
        return {
            "ok": True,
            "status": "created",
            "chosen": chosen,
            "diagnosis": data2.get("diagnosis"),
        }
    
    return {"ok": True, **data}

@mcp.tool()
def hl7_build_adt_a04(patient_id: int) -> dict:
    """Build a deterministic HL7 v2.5 ADT^A04 registration message for the patient using their stored diagnoses. Saves the message to the database and returns the HL7 text. ALWAYS call this together with blockchain_record_admission when admitting a patient — both must be called for every admission."""
    _count("hl7_build_adt_a04")

    r = httpx.post(
        f"{API_BASE}/hl7/build/adt_a04",
        json={"patient_id": patient_id},
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
def hl7_send(message_id: int) -> dict:
    """Send a built HL7 message to the mock receiver via MLLP. Returns ACK or NACK status and stores the result in the database."""

    _count("hl7_send")

    r = httpx.post(
        f"{API_BASE}/hl7/send",
        json={"message_id": message_id},
        timeout = 15.0,
    )

    try:
        data = r.json()
    except Exception:
        data = {"error": "bad_response", "status_code": r.status_code}
    
    if r.status_code >= 400:
        return {"ok": False, "status_code": r.status_code, "error": data}
    
    return {"ok": True, **data}


@mcp.tool()
def blockchain_record_admission(patient_id: int, message_type: str = "ADT^A04") -> dict:
    """Record a patient admission event on the blockchain audit log. Call this in parallel with hl7_build_adt_a04 when admitting a patient."""
    _count("blockchain_record_admission")

    r = httpx.post(
        f"{BLOCKCHAIN_API_BASE}/blockchain/record_admission",
        json={"patient_id": patient_id, "message_type": message_type},
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
def blockchain_record_diagnosis(patient_id: int, icd_code: str) -> dict:
    """Record a diagnosis event on the blockchain audit log for a patient."""
    _count("blockchain_record_diagnosis")

    r = httpx.post(
        f"{BLOCKCHAIN_API_BASE}/blockchain/record_diagnosis",
        json={"patient_id": patient_id, "icd_code": icd_code},
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

@mcp.prompt()
def admit_patient(patient_id: int) -> str:
    return (
        f"Admit patiennt {patient_id}: "
        f"call both hl7_build_adt_a04(patient_id = {patient_id})"
        f"and blockchain_record_admission(patient_id = {patient_id}) in parallel, "
        f"then call hl7_send with the returned message_id."
    )

def main():
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
