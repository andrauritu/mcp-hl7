import csv
from pathlib import Path

from db import get_conn, init_db

CSV_PATH = Path(__file__).with_name("data") / "atc.csv"

def ingest() -> int:
    init_db()
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"ATC CSV file not found at {CSV_PATH}")

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"atc_code", "atc_name"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise RuntimeError("CSV file missing required columns (atc_code, atc_name)")

        rows = []
        for row in reader:
            code = (row.get("atc_code") or "").strip()
            name = (row.get("atc_name") or "").strip()
            if not code or not name:
                continue
            ddd = (row.get("ddd") or "").strip() or None
            uom = (row.get("uom") or "").strip() or None
            adm_r = (row.get("adm_r") or "").strip() or None
            # skip NA values
            if ddd == "NA":
                ddd = None
            if uom == "NA":
                uom = None
            if adm_r == "NA":
                adm_r = None
            rows.append((code, name, ddd, uom, adm_r))

    with get_conn() as conn:
        conn.execute("DELETE FROM atc_codes")
        conn.execute("DELETE FROM atc_fts")
        conn.executemany(
            """INSERT OR REPLACE INTO atc_codes
               (code, name, ddd, uom, adm_route)
               VALUES (?, ?, ?, ?, ?)""",
            rows,
        )
        fts_rows = [(r[0], r[1]) for r in rows]
        conn.executemany(
            "INSERT INTO atc_fts (code, name) VALUES (?, ?)",
            fts_rows,
        )
        conn.commit()

    return len(rows)


if __name__ == "__main__":
    n = ingest()
    print(f"Ingested {n} ATC codes.")
