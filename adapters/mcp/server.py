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


def main():
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
