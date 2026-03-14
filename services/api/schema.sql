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

CREATE VIRTUAL TABLE IF NOT EXISTS icd_fts
USING fts5(code, description);

CREATE INDEX IF NOT EXISTS idx_icd_code ON icd_codes(code);

CREATE TABLE IF NOT EXISTS diagnoses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    icd_code TEXT NOT NULL,
    term TEXT, 
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (patient_id) REFERENCES patients(id),
    FOREIGN KEY (icd_code) REFERENCES icd_codes(code)
);

CREATE INDEX IF NOT EXISTS idx_diagnoses_patient ON diagnoses(patient_id);
CREATE INDEX IF NOT EXISTS idx_diagnoses_icd ON diagnoses(icd_code);

CREATE TABLE IF NOT EXISTS hl7_messages(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    message_type TEXT NOT NULL,
    hl7_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'built',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS hl7_messages(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    message_type TEXT NOT NULL,
    hl7_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'built',
    ack_text TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

CREATE INDEX IF NOT EXISTS idx_hl7_patient ON hl7_messages(patient_id);
CREATE INDEX IF NOT EXISTS idx_hl7_status ON hl7_messages(status);