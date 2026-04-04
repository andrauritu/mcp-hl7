import logging
import sys
import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
mcp = FastMCP("hl7-mcp")

API_BASE = "http://127.0.0.1:8000"

_TOOL_COUNTS: dict[str, int] = {}

def _count(tool_name: str) -> None:
    _TOOL_COUNTS[tool_name] = _TOOL_COUNTS.get(tool_name, 0) + 1


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
    _count("patient_create")
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
def patient_list(limit: int = 50) -> dict:
    """List all patients in the system, ordered by most recently created first."""
    _count("patient_list")
    limit = max(1, min(200, limit))
    r = httpx.get(f"{API_BASE}/patients", params={"limit": limit}, timeout=5.0)
    try:
        data = r.json()
    except Exception:
        data = {"error": "bad_response", "status_code": r.status_code}
    if r.status_code >= 400:
        return {"ok": False, "status_code": r.status_code, "error": data}
    return {"ok": True, **data}


@mcp.tool()
def patient_get(patient_id: int) -> dict:
    """Get a patient record by their numeric ID."""
    _count("patient_get")
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
    _count("icd_search")
    limit = max(1, min(20, limit))
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
    _count("icd_get")
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


@mcp.tool()
def patient_add_diagnosis(patient_id: int, term: str, auto_select: bool = True, limit: int = 5) -> dict:
    """Search ICD-10 for term and add the top match as a diagnosis for the patient.
    Also records the diagnosis on the blockchain audit log.
    If auto_select is False, returns candidates for manual selection."""
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
        r2 = httpx.post(
            f"{API_BASE}/patients/{patient_id}/diagnoses",
            json={"term": term, "icd_code": chosen["code"]},
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
            "blockchain": data2.get("blockchain"),
        }

    return {"ok": True, **data}


@mcp.tool()
def record_admission(patient_id: int) -> dict:
    """Admit a patient: builds the HL7 ADT^A04 message, sends it to the HL7 receiver via MLLP,
    and records the admission on the blockchain audit log — all in one call."""
    _count("record_admission")
    r = httpx.post(
        f"{API_BASE}/admissions",
        json={"patient_id": patient_id},
        timeout=30.0,
    )
    try:
        data = r.json()
    except Exception:
        data = {"error": "bad_response", "status_code": r.status_code}
    if r.status_code >= 400:
        return {"ok": False, "status_code": r.status_code, "error": data}
    return {"ok": True, **data}


@mcp.tool()
def patient_add_prescription(
    patient_id: int,
    medication_name: str,
    dose: str,
    unit: str,
    frequency: str,
    route: str = "oral",
    prescriber: str = "Dr. MCP",
    icd_code: str = "",
) -> dict:
    """Create a prescription for a patient: builds HL7 RDE^O11, sends via MLLP,
    and records on blockchain — all in one call.
    Example: patient_add_prescription(1, "Metformin", "500", "mg", "twice daily", "oral")"""
    _count("patient_add_prescription")
    r = httpx.post(
        f"{API_BASE}/patients/{patient_id}/prescriptions",
        json={
            "medication_name": medication_name,
            "dose": dose,
            "unit": unit,
            "frequency": frequency,
            "route": route,
            "prescriber": prescriber,
            "icd_code": icd_code or None,
        },
        timeout=30.0,
    )
    try:
        data = r.json()
    except Exception:
        data = {"error": "bad_response", "status_code": r.status_code}
    if r.status_code >= 400:
        return {"ok": False, "status_code": r.status_code, "error": data}
    return {"ok": True, **data}


@mcp.tool()
def get_usage_stats() -> dict:
    """Return how many times each MCP tool has been called in this session."""
    _count("get_usage_stats")
    return {"ok": True, "counts": dict(_TOOL_COUNTS)}


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
