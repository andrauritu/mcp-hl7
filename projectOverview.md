# Project Overview: MCP-HL7

A full-stack **healthcare interoperability platform** that integrates **HL7 v2.5 messaging**, **blockchain audit logging**, **medical coding (ICD-10 + ATC)**, and an **MCP adapter layer** for AI agent interaction — all orchestrated with **Docker Compose**.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     AI Agent (Claude / LLM)                     │
│                            via MCP                              │
└───────┬────────────────────────────┬────────────────────────────┘
        │ stdio                      │ stdio
┌───────▼───────────┐   ┌───────────▼──────────────┐
│  MCP Adapter      │   │  MCP Blockchain Adapter   │
│  adapters/mcp/    │   │  adapters/mcp-blockchain/ │
│  :httpx→:8000     │   │  :httpx→:8000 & :8001     │
└───────┬───────────┘   └───────────┬──────────────┘
        │ HTTP                      │ HTTP
┌───────▼───────────────────────────▼──────────────┐
│           Main API + Dashboard (Flask :8000)       │
│                  services/api/                      │
│  SQLite (patients, diagnoses, prescriptions, HL7)  │
│  ICD-10 FTS5 · ATC FTS5 · Jinja2 Dashboard        │
└──────┬──────────────────┬────────────────────────┘
       │ TCP/MLLP :2575   │ HTTP :8001
┌──────▼──────────┐  ┌────▼──────────────────────────┐
│  HL7 Receiver   │  │  Blockchain API (Flask :8001)  │
│  services/       │  │  services/blockchain_api/      │
│  hl7_receiver/   │  │  Web3.py → Hardhat EVM        │
└─────────────────┘  └────┬───────────────────────────┘
                          │ JSON-RPC :8545
                     ┌────▼───────────────────┐
                     │  Hardhat Node (EVM)     │
                     │  contracts/             │
                     │  MedicalAudit.sol       │
                     └────────────────────────┘
```

---

## 1. Smart Contract Layer — `contracts/`

| File | Purpose |
|---|---|
| `contracts/MedicalAudit.sol` | Solidity 0.8.28 audit contract — **events-only design** (no on-chain state storage, gas-efficient). Emits `AdmissionRecorded`, `DiagnosisRecorded`, `PrescriptionRecorded` |
| `hardhat.config.js` | Hardhat config — Solidity 0.8.28, `localhost` network pointed at `HARDHAT_URL` env var (default `127.0.0.1:8545`) |
| `scripts/deploy.js` | Deployment script — deploys `MedicalAudit`, writes contract address to `deployed.json` |
| `Dockerfile` | `node:20-slim`, `npm install`, `hardhat compile`, runs `hardhat node` on port 8545 |
| `package.json` | Hardhat toolbox, ethers v6, solidity-coverage, gas-reporter, typechain |

### Smart Contract Functions

- `recordAdmission(uint256 patientId, string messageType)` → emits `AdmissionRecorded`
- `recordDiagnosis(uint256 patientId, string icdCode)` → emits `DiagnosisRecorded`
- `recordPrescription(uint256 patientId, string medication, string icdCode)` → emits `PrescriptionRecorded`

All events have an indexed `patientId` and a `timestamp` from `block.timestamp`.

---

## 2. Main API + Dashboard — `services/api/`

### Core Files

| File | Purpose |
|---|---|
| `app.py` | Flask application — 15 routes, CORS, all business logic |
| `db.py` | SQLite connection manager — context-manager `get_db()`, auto-commit/rollback |
| `schema.sql` | 6 tables + FTS5 virtual tables + indexes |
| `hl7_builder.py` | Builds HL7 v2.5 messages: `ADT^A04` (admission) and `RDE^O11` (pharmacy order) |
| `mllp_client.py` | Raw TCP MLLP client — wraps HL7 in `\x0b...\x1c\x0d` framing, parses ACK/NACK |
| `ingest_icd.py` | Ingests ICD-10 codes from CSV into SQLite + FTS5 index |
| `ingest_atc.py` | Ingests WHO ATC medication codes from CSV into SQLite + FTS5 index |
| `templates/dashboard.html` | Single-page Tailwind CSS dashboard with full JS frontend |
| `data/icd.csv` | ICD-10 code dataset |
| `data/atc.csv` | WHO ATC code dataset (~6807 medications) |
| `Dockerfile` | `python:3.12-slim`, installs Flask+requests, runs ICD+ATC ingestion at build time |

### Database Schema (SQLite)

| Table | Columns | Notes |
|---|---|---|
| `patients` | id, name, dob, sex, created_at | Core patient registry |
| `icd_codes` | code (PK), description, chapter, section, category, category_code | ~73K ICD-10 codes |
| `icd_fts` | code, description | FTS5 virtual table for full-text search |
| `atc_codes` | code (PK), name, ddd, uom, adm_route | ~6807 WHO ATC medication codes |
| `atc_fts` | code, name | FTS5 virtual table for medication search |
| `diagnoses` | id, patient_id (FK), icd_code (FK), term, created_at | Patient diagnoses |
| `prescriptions` | id, patient_id (FK), medication_name, atc_code (FK), dose, unit, frequency, route, prescriber, icd_code (FK), created_at | Prescriptions |
| `hl7_messages` | id, patient_id (FK), message_type, hl7_text, status, ack_text, created_at | HL7 message audit trail |

### API Routes

| Method | Route | Description |
|---|---|---|
| GET | `/` | Redirects to `/dashboard` |
| GET | `/dashboard` | Serves the Jinja2 HTML dashboard |
| GET | `/health` | Health check |
| POST | `/patients` | Create patient (name, dob, sex) |
| GET | `/patients` | List patients (with limit) |
| GET | `/patients/<id>` | Get single patient |
| GET | `/patients/full` | Patients with embedded diagnoses + prescriptions (dashboard) |
| GET | `/icd/search?q=...` | 3-tier ICD-10 search: code prefix → FTS5/BM25 → LIKE fallback |
| GET | `/icd/<code>` | Get single ICD-10 code |
| GET | `/atc/search?q=...` | 3-tier ATC search: code prefix → FTS5/BM25 → LIKE fallback |
| GET | `/atc/<code>` | Get single ATC code |
| POST | `/patients/<id>/diagnoses` | Add diagnosis (auto-search or direct ICD code). Records on blockchain. |
| GET | `/patients/<id>/diagnoses` | List patient's diagnoses |
| POST | `/admissions` | **Atomic operation**: build HL7 ADT^A04 → send MLLP → record on blockchain (parallel) |
| POST | `/hl7/build/adt_a04` | Build HL7 only (no send) |
| POST | `/hl7/send` | Send a previously built HL7 message |
| POST | `/patients/<id>/prescriptions` | **Atomic operation**: create rx → build HL7 RDE^O11 → send MLLP → record on blockchain (parallel) |
| GET | `/patients/<id>/prescriptions` | List patient's prescriptions |

### HL7 v2.5 Messages

**ADT^A04** (Register Patient):
- Segments: `MSH`, `PID`, `DG1` (one per diagnosis)
- PID carries patient ID, name, DOB, sex
- DG1 carries ICD-10 code + description

**RDE^O11** (Pharmacy Order):
- Segments: `MSH`, `PID`, `ORC` (order control), `RXE` (pharmacy encoded order), optionally `DG1`
- RXE-2 uses HL7 CE (Coded Element) format: `ATC_CODE^medication_name^ATC` when ATC code is present
- RXE carries dose, unit, frequency, route

### Dashboard Frontend

Single HTML file using:
- **Tailwind CSS** (CDN) + custom design system (coral/teal/sage/apricot palette, "bento-card" components)
- **Font Awesome 6.4** for icons
- **Inter** + **Playfair Display** fonts

**4 Action Cards** (top row, `grid-cols-4`):
1. **New Patient** — form: name, DOB, sex
2. **Diagnosis** — ICD-10 autocomplete dropdown with debounced search
3. **Prescription** — ATC autocomplete dropdown with debounced search, plus dose/unit/frequency/route
4. **Admit Patient** — one-click admission

**Data Zone Row 1** (`grid-cols-12`):
- **Patient Directory** (8 cols) — scrollable table (`clamp(320px, 52vh, 680px)`) with sticky headers, ICD/ATC badges
- **Chain Lens** (4 cols) — dark card showing live blockchain events, filters (All/Admissions/Diagnoses/Prescriptions), search, pagination, real-time stats

**Data Zone Row 2** (`grid-cols-2`):
- **Patient Timeline** — load by patient ID, shows chronological on-chain history
- **Smart Contract Audit** — ABI introspection, gas estimates, security checks

---

## 3. Blockchain API — `services/blockchain_api/`

| File | Purpose |
|---|---|
| `app.py` | Flask :8001 — blockchain transaction endpoints |
| `contract.py` | Web3.py contract loader — reads `deployed.json` + ABI artifacts, connects to Hardhat |
| `Dockerfile` | `python:3.12-slim`, installs Flask + web3 |

### API Routes

| Method | Route | Description |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/blockchain/record_admission` | Calls `recordAdmission()` on-chain, returns tx hash + block + gas |
| POST | `/blockchain/record_diagnosis` | Calls `recordDiagnosis()` on-chain |
| POST | `/blockchain/record_prescription` | Calls `recordPrescription()` on-chain |
| GET | `/blockchain/events` | All events across all patients (paginated, sorted by block desc) |
| GET | `/blockchain/events/<patient_id>` | All events for one patient (admissions + diagnoses + prescriptions) |
| GET | `/blockchain/contract/audit` | Full contract introspection — ABI functions/events, gas estimates, bytecode size, 6-point security checklist (selfdestruct, delegatecall, callcode, events-only design, access control, non-payable) |

---

## 4. HL7 MLLP Receiver — `services/hl7_receiver/`

| File | Purpose |
|---|---|
| `receiver.py` | Standalone TCP socket server on port 2575 |
| `Dockerfile` | `python:3.12-slim`, runs `receiver.py` |

**Protocol:** MLLP (Minimal Lower Layer Protocol) — `\x0b` start, `\x1c\x0d` end framing.

**Validation:** Checks for MSH and PID segments. Returns:
- `MSA|AA` (ACK) if valid
- `MSA|AE` (NACK) if invalid, with ERR segment describing the problem

Logs all incoming connections and messages.

---

## 5. MCP Adapters — `adapters/`

### `adapters/mcp/` — Patient & Clinical MCP Server

10 tools exposed over **stdio** transport for AI agents:

| Tool | Description |
|---|---|
| `ping` | Health check |
| `patient_create` | Create patient |
| `patient_list` | List patients |
| `patient_get` | Get patient by ID |
| `icd_search` | Search ICD-10 codes |
| `icd_get` | Get single ICD code |
| `patient_add_diagnosis` | Search + auto-select + add diagnosis + blockchain (one call) |
| `record_admission` | Full admission pipeline: HL7 build → MLLP send → blockchain |
| `patient_add_prescription` | Full prescription pipeline: create → HL7 → MLLP → blockchain |
| `get_usage_stats` | Session tool call counts |

### `adapters/mcp-blockchain/` — Blockchain Audit MCP Server

5 tools over **stdio**:

| Tool | Description |
|---|---|
| `blockchain_get_events` | Get all chain events for a patient |
| `blockchain_get_all_events` | Browse all events paginated |
| `blockchain_verify_patient` | **Cross-validates** DB records vs blockchain — detects discrepancies (missing audit events, phantom records) |
| `blockchain_audit_summary` | Chronological audit timeline from on-chain data |
| `blockchain_audit_contract` | Full smart contract security audit |

---

## 6. Docker Compose — `docker-compose.yml`

5 services orchestrated with dependency chain:

```
hardhat (node, :8545)
    ↓ healthcheck: eth_blockNumber
deploy-contract (one-shot, same image)
    ↓ condition: service_completed_successfully
blockchain-api (flask, :8001)   ←── reads deployed.json + ABI via shared volume
    ↓
api (flask, :8000)              ←── depends on blockchain-api + hl7-receiver
hl7-receiver (python, :2575)    ←── independent
```

**Shared volume:** `contracts-data` — hardhat writes compiled artifacts + `deployed.json`, deploy-contract writes the address, blockchain-api reads them (`:ro`).

**Environment variable wiring:**
- `HARDHAT_URL=http://hardhat:8545` (blockchain-api + deploy-contract)
- `CONTRACTS_DIR=/contracts` (blockchain-api)
- `BLOCKCHAIN_API_URL=http://blockchain-api:8001` (api)
- `HL7_RECEIVER_HOST=hl7-receiver` / `HL7_RECEIVER_PORT=2575` (api)

### Running

```bash
# Start everything (first time builds all images)
docker compose up --build

# Stop
docker compose down

# Stop + wipe blockchain volume (fresh chain)
docker compose down -v
```

---

## 7. Data Flow: End-to-End Example

**"Admit Patient #20":**

1. Dashboard JS → `POST /admissions {patient_id: 20}`
2. API fetches patient + diagnoses from SQLite
3. `hl7_builder.build_adt_a04()` constructs the HL7 v2.5 message with MSH, PID, DG1 segments
4. **In parallel** (ThreadPoolExecutor):
   - `mllp_client.send()` → TCP to HL7 Receiver :2575 → gets ACK/NACK → updates `hl7_messages` table
   - `requests.post()` → Blockchain API :8001 → `recordAdmission()` on Solidity contract → Hardhat EVM → emits `AdmissionRecorded` event → returns tx hash + block number
5. API returns combined result to dashboard
6. Dashboard Chain Lens polls `/blockchain/events` and shows the new event card

---

## 8. File Count Summary

| Area | Files | Key Tech |
|---|---|---|
| Smart contracts | 4 source + config | Solidity 0.8.28, Hardhat, ethers.js |
| Main API | 9 source + 1 template + 2 CSVs | Flask, SQLite, FTS5, HL7 v2.5 |
| Blockchain API | 2 source | Flask, Web3.py |
| HL7 Receiver | 1 source | Raw TCP sockets, MLLP protocol |
| MCP Adapters | 2 servers (2 source) | FastMCP, httpx, stdio transport |
| Infrastructure | 4 Dockerfiles + 1 compose | Docker, shared volumes |
| **Total** | **~25 source files** | |
