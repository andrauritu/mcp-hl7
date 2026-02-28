import logging
import sys
import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
mcp = FastMCP("hl7-mcp")

API_BASE = "http://127.0.0.1:8000"

@mcp.tool()
def ping() -> str:
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
    _count("get_usage_stats")
    return {"ok": True, "counts": dict(_TOOL_COUNTS)}


@mcp.tool()
def patient_add_diagnosis(patient_id: int, term: str, auto_select: bool = True, limit: int = 5) -> dict:
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


def main():
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
