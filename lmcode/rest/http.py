"""HTTP/1.1 subset framing for the `rest` std module (spec/std-rest.md, "HTTP subset"). Bytes are latin-1 strings."""
from __future__ import annotations
import re
from typing import List, Tuple

MAX_HEADER_BYTES = 16 * 1024
_REASONS = {200: "OK", 201: "Created", 202: "Accepted", 204: "No Content", 301: "Moved Permanently", 302: "Found",
            304: "Not Modified", 400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found",
            405: "Method Not Allowed", 408: "Request Timeout", 409: "Conflict", 413: "Payload Too Large",
            415: "Unsupported Media Type", 422: "Unprocessable Entity", 429: "Too Many Requests",
            431: "Request Header Fields Too Large", 500: "Internal Server Error", 501: "Not Implemented",
            502: "Bad Gateway", 503: "Service Unavailable"}
ERRORS = {400: b'{"error":"bad request"}', 404: b'{"error":"not found"}', 405: b'{"error":"method not allowed"}',
          413: b'{"error":"payload too large"}', 431: b'{"error":"request header too large"}',
          500: b'{"error":"internal error"}', 501: b'{"error":"not implemented"}'}
_REQUEST_LINE = re.compile(r"([A-Z]+) ([^\x00-\x20\x7f]+) HTTP/1\.[01]")
_NAME_BAD = re.compile(r"[\x00-\x20\x7f]")
_LINE_BAD = re.compile(r"[\x00-\x08\x0a-\x1f\x7f]")
_DIGITS = re.compile(r"[0-9]{1,15}")
_LOWER = {c: c + 32 for c in range(65, 91)}


def ascii_lower(text: str) -> str:
    """Lower-case ASCII letters only (header names are bytes, not Unicode text)."""
    return text.translate(_LOWER)


def reason_phrase(status: int) -> str:
    if status in _REASONS:
        return _REASONS[status]
    return "OK" if status < 300 else "Redirect" if status < 400 else "Client Error" if status < 500 else "Server Error"


class Request:
    def __init__(self, method: str, target: str, headers: List[Tuple[str, str]], body: bytes = b""):
        self.method, self.target, self.headers, self.body = method, target, headers, body

    def __repr__(self):
        return "Request(%r, %r, %r, %r)" % (self.method, self.target, self.headers, self.body)


class Response:
    def __init__(self, status: int, headers: List[Tuple[str, str]], body: bytes = b""):
        self.status, self.headers, self.body = status, headers, body

    def __repr__(self):
        return "Response(%r, %r, %r)" % (self.status, self.headers, self.body)

    def __eq__(self, other):
        return isinstance(other, Response) and (self.status, self.headers, self.body) == (other.status, other.headers, other.body)


def error_response(status: int, extra: List[Tuple[str, str]] = ()) -> Response:
    return Response(status, [("Content-Type", "application/json")] + list(extra), ERRORS[status])


def parse_head(text: str):
    """Parse a header section (latin-1, without the blank line). Returns (method, target, headers) or an int error status."""
    lines = text.split("\r\n")
    m = _REQUEST_LINE.fullmatch(lines[0])
    if not m:
        return 400
    method, target = m.group(1), m.group(2)
    if not target.startswith("/") or "#" in target:
        return 400
    headers = []
    for line in lines[1:]:
        colon = line.find(":")
        if colon <= 0 or _NAME_BAD.search(line[:colon]) or _LINE_BAD.search(line):
            return 400
        headers.append((line[:colon], line[colon + 1:].strip(" \t")))
    return method, target, headers


def body_length(headers):
    """Returns (length, None) or (None, error_status). Transfer-Encoding is unsupported (501)."""
    if any(ascii_lower(n) == "transfer-encoding" for n, _ in headers):
        return None, 501
    values = [v for n, v in headers if ascii_lower(n) == "content-length"]
    if not values:
        return 0, None
    if len(values) > 1 and len(set(values)) > 1:
        return None, 400
    if not _DIGITS.fullmatch(values[0]):
        return None, 400
    return int(values[0]), None


def encode_response(response: Response, head: bool = False) -> bytes:
    lines = ["HTTP/1.1 %d %s" % (response.status, reason_phrase(response.status))]
    for name, value in response.headers:
        lines.append(name + ": " + value)
    lines.extend(["Content-Length: %d" % len(response.body), "", ""])
    data = "\r\n".join(lines).encode("latin-1")
    return data if head else data + response.body


def take_request(buffer: bytes, max_body_bytes: int):
    """Take one request off the front of `buffer`.

    Returns ("need", None), ("fatal", status) or ("request", (Request, rest)). A fatal framing error ends serving.
    """
    end = buffer.find(b"\r\n\r\n")
    if end < 0:
        return ("fatal", 431) if len(buffer) > MAX_HEADER_BYTES else ("need", None)
    if end > MAX_HEADER_BYTES:
        return "fatal", 431
    head = parse_head(buffer[:end].decode("latin-1"))
    if isinstance(head, int):
        return "fatal", head
    length, error = body_length(head[2])
    if error:
        return "fatal", error
    if length > max_body_bytes:
        return "fatal", 413
    start = end + 4
    if len(buffer) < start + length:
        return "need", None
    return "request", (Request(head[0], head[1], head[2], bytes(buffer[start:start + length])), buffer[start + length:])
