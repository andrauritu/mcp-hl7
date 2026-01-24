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

def main():
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
