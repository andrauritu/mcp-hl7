import csv
from pathlib import Path

from db import get_conn, init_db

CSV_PATH = Path(__file__).with_name("data") / "icd.csv"

def ingest() -> int:
    init_db
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"ICD CSV file not found at {CSV_PATH}")
    
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"code", "description"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise RuntimeError("CSV file missing required columns")
        
        rows = []
        for row in reader:
            code = (row.get("code") or "").strip()
            desc = (row.get("description") or "").strip()
            if not code or not desc:
                continue
            rows.append((
                code,
                desc,
                row.get("chapter" or "").strip() or None,
                row.get("section" or "").strip() or None,
                row.get("category" or "").strip() or None,
                row.get("category_code" or "").strip() or None,

            ))

    with get_conn() as conn:

        conn.execute("DELETE FROM icd_codes")
        conn.executemany(
            """
            INSERT OR REPLACE INTO icd_codes
            (code, description, chapter, section, category, category_code)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()

    return len(rows)


if __name__ == "__main__":
    n = ingest()
    print(f"Ingested {n} ICD codes.")