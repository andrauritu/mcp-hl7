from datetime import datetime, timezone

_SEGMENT_SEP = "\r"
_FIELD_SEP = "|"
_ENCODING_CHARS = "^~\\&"

def build_adt_a04(
    patient_id: str,
    patient_name: str,
    dob: str,
    sex: str,
    diagnoses: list[dict],
    message_control_id: str | None = None,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    if message_control_id is None:
        message_control_id = f"{patient_id}-{now}"

    segments = []

    msh = _FIELD_SEP.join([
        "MSH",
        _ENCODING_CHARS,
        "MCPHL7",
        "DEMO",
        "EHR",
        "DEMO",
        now,
        "",
        "ADT^A04",
        message_control_id,
        "P",
        "2.5",
    ])

    segments.append(msh)

    pid = _FIELD_SEP.join([
        "PID",
        "1",
        "",
        str(patient_id),
        "",
        patient_name,
        "",
        _format_dob(dob),
        sex,
    ])
    segments.append(pid)

    for i, dx in enumerate(diagnoses, start=1):
        dg1 = _FIELD_SEP.join([
            "DG1",
            str(i),
            "I10",
            dx["icd_code"],
            dx.get("description", ""),
            "",
            "A",
        ])
        segments.append(dg1)

    return _SEGMENT_SEP.join(segments)

def _format_dob(dob: str) -> str:
    return dob.replace("-", "")


def build_rde_o11(
    patient_id: str,
    patient_name: str,
    dob: str,
    sex: str,
    medication_name: str,
    dose: str,
    unit: str,
    frequency: str,
    route: str,
    prescriber: str = "Dr. MCP",
    atc_code: str | None = None,
    icd_code: str | None = None,
    icd_description: str | None = None,
    message_control_id: str | None = None,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    if message_control_id is None:
        message_control_id = f"RX-{patient_id}-{now}"

    segments = []

    msh = _FIELD_SEP.join([
        "MSH",
        _ENCODING_CHARS,
        "MCPHL7",
        "DEMO",
        "PHARMACY",
        "DEMO",
        now,
        "",
        "RDE^O11",
        message_control_id,
        "P",
        "2.5",
    ])
    segments.append(msh)

    pid = _FIELD_SEP.join([
        "PID",
        "1",
        "",
        str(patient_id),
        "",
        patient_name,
        "",
        _format_dob(dob),
        sex,
    ])
    segments.append(pid)

    orc = _FIELD_SEP.join([
        "ORC",
        "NW",
        message_control_id,
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        prescriber,
    ])
    segments.append(orc)

    # RXE-2: Give Code — use HL7 CE (Coded Element): code^text^coding_system
    if atc_code:
        give_code = f"{atc_code}^{medication_name}^ATC"
    else:
        give_code = medication_name

    rxe = _FIELD_SEP.join([
        "RXE",
        "",
        give_code,
        dose,
        unit,
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        frequency,
        "",
        route,
    ])
    segments.append(rxe)

    if icd_code:
        dg1 = _FIELD_SEP.join([
            "DG1",
            "1",
            "I10",
            icd_code,
            icd_description or "",
            "",
            "A",
        ])
        segments.append(dg1)

    return _SEGMENT_SEP.join(segments)
        
