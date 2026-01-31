CREATE TABLE IF NOT EXISTS patients(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    dob TEXT NOT NULL,
    sex TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS icd_codes (
    code TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    chapter TEXT,
    section TEXT,
    category TEXT,
    category_code TEXT
);

CREATE INDEX IF NOT EXISTS idx_icd_description ON icd_codes(description);
