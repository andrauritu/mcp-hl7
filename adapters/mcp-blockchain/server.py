import logging
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import PromptMessage, TextContent

logging.basicConfig(level=logging.INFO)
mcp = FastMCP("hl7-mcp-blockchain")

BLOCKCHAIN_API_BASE = "http://127.0.0.1:8001"

_TOOL_COUNTS: dict[str, int] = {}

def _count(tool_name: str) -> None:
    _TOOL_COUNTS[tool_name] = _TOOL_COUNTS.get(tool_name, 0) + 1

@mcp.tool()
def blockchain_record_admission(patient_id: int, message_type: str = "ADT^A04") -> dict:
    """Record a patient admission event on the blockchain audit log. ALWAYS call this together with hl7_build_adt_a04 when admitting a patient — both must be called for every admission."""
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
