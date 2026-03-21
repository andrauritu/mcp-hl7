import logging
import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
mcp = FastMCP("hl7-mcp-blockchain")

BLOCKCHAIN_API_BASE = "http://127.0.0.1:8001"

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


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
