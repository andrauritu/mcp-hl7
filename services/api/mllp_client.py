import os
import socket
import ssl

MLLP_START = b"\x0b"
MLLP_END = b"\x1c\x0d"

RECEIVER_HOST = os.environ.get("HL7_RECEIVER_HOST", "127.0.0.1")
RECEIVER_PORT = int(os.environ.get("HL7_RECEIVER_PORT", "2575"))
TLS_CA = os.environ.get("HL7_TLS_CA", "/app/hl7_receiver_cert.pem")

def send(hl7_text: str, host: str = RECEIVER_HOST, port: int = RECEIVER_PORT) -> str:
    payload = MLLP_START + hl7_text.encode("utf-8") + MLLP_END

    tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    tls_context.load_verify_locations(cafile=TLS_CA)

    raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw_sock.settimeout(10.0)
    sock = tls_context.wrap_socket(raw_sock, server_hostname=host)
    try:
        try:
            sock.connect((host, port))
        except OSError as e:
            raise ConnectionError(f"Could not reach HL7 receiver at {host}:{port}") from e

        sock.sendall(payload)

        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
            if MLLP_END in response:
                break
    finally:
        sock.close()

    start = response.find(MLLP_START)
    end = response.find(MLLP_END)

    if start == -1 or end == -1:
        return response.decode("utf-8", errors="replace")

    return response[start + 1 : end].decode("utf-8", errors="replace")


def is_ack(hl7_response: str) -> bool:
    for segment in hl7_response.split("\r"):
        if segment.startswith("MSA"):
            fields = segment.split("|")
            if len(fields) > 1:
                return fields[1].strip() == "AA"
    return False
