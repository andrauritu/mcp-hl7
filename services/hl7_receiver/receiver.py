import socket
import logging

HOST = "127.0.0.1"
PORT = 2575

MLLP_START = b"\x0b"
MLLP_END = b"\x1c\x0d"  

logging.basicConfig(level=logging.INFO, format = "%(asctime)s %(message)s" )

def build_ack(message_control_id: str, ack_code: str, error_msg: str = " ") -> bytes:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    msh = f"MSH|^~\\&|EHR|DEMO|MCPHL7|DEMO|{now}||ACK|ACK-{now}|P|2.5"
    msa = f"MSA|{ack_code}|{message_control_id}"

    segments = [msh, msa]
    if error_msg:
        segments.append(f"ERR|||{error_msg}")

    hl7 = "\r".join(segments)
    return MLLP_START + hl7.encode("utf-8") + MLLP_END

def validate(hl7_text: str) -> tuple[bool, str]:
    segments = [s.strip() for s in hl7_text.split("\r") if s.strip()]
    names = [s.split("|")[0] for s in segments]

    if "MSH" not in names:
        return False, "Missing MSH segment"
    if "PID" not in names:
        return False, "Missing PID segment"
    return True, ""

def extract_message_control_id(hl7_text: str) -> str:
    for segment in hl7_text.split("\r"):
        if segment.startswith("MSH|"):
            fields = segment.split("|")
            if len(fields) > 9:
                return fields[9]
    return "UNKNOWN"

def handle_connection (conn: socket.socket, addr: tuple) -> None:
    logging.info(f"Connection from {addr}")

    with conn:
        raw = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            raw += chunk

            if MLLP_END in raw:
                break

        start = raw.find(MLLP_START)
        end = raw.find(MLLP_END)
        if start == -1 or end == -1:
            logging.warning("Invalid MLLP framing - dropping connection")
            return
        
        hl7_text = raw[start + 1 : end].decode("utf-8", errors = "replace")
        logging.info(f"Received HL7 message ({len(hl7_text)} chars)")

        control_id = extract_message_control_id(hl7_text)
        ok, error_msg = validate(hl7_text)

        if ok:
            logging.info(f"Valid message - sending ACK (control_id={control_id})")
            conn.sendall(build_ack(control_id, "AA"))
        else:
            logging.warning(f"Invalid message - sending NACK: {error_msg}")
            conn.sendall(build_ack(control_id, "AE", error_msg))


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, PORT))
        srv.listen(5)
        logging.info(f"HL7 Receiver listening on {HOST}:{PORT}")
        while True:
            conn, addr = srv.accept()
            handle_connection(conn, addr)

if __name__ == "__main__":
    main()
