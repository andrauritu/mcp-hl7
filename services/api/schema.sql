CREATE TABLE IF NOT EXISTS patients(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    dob TEXT NOT NULL,
    sex TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    discharged_at TEXT
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

CREATE TABLE IF NOT EXISTS atc_codes (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    ddd TEXT,
    uom TEXT,
    adm_route TEXT
);

CREATE INDEX IF NOT EXISTS idx_atc_name ON atc_codes(name);

CREATE VIRTUAL TABLE IF NOT EXISTS atc_fts
USING fts5(code, name);

CREATE INDEX IF NOT EXISTS idx_atc_code ON atc_codes(code);

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

CREATE TABLE IF NOT EXISTS prescriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    medication_name TEXT NOT NULL,
    atc_code TEXT,
    dose TEXT NOT NULL,
    unit TEXT NOT NULL,
    frequency TEXT NOT NULL,
    route TEXT NOT NULL DEFAULT 'oral',
    prescriber TEXT NOT NULL DEFAULT 'Dr. MCP',
    icd_code TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (patient_id) REFERENCES patients(id),
    FOREIGN KEY (icd_code) REFERENCES icd_codes(code),
    FOREIGN KEY (atc_code) REFERENCES atc_codes(code)
);

CREATE INDEX IF NOT EXISTS idx_prescriptions_patient ON prescriptions(patient_id);

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