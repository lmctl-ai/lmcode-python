"""Replay of conformance/rest-suite/scenarios.json (groups stream, fatal, silent) against the rest controller.

Used by tests/test_rest_suite.py and scripts/run-rest-suite.py. Two levels: in-memory streams, and a real child
process (python -m lmcode.rest) driven over its stdin/stdout pipes. No network is involved.
"""
import io
import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from lmcode import Registry, load  # noqa: E402
from lmcode.rest import register_rest  # noqa: E402

DIR = ROOT / "conformance" / "rest-suite"
SUITE = json.loads((DIR / "scenarios.json").read_text(encoding="utf-8"))
GOOD = b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n"


def request_bytes(s):
    if "raw" in s:
        return s["raw"].encode("latin-1")
    if "body_repeat" in s:
        body = (s["body_repeat"]["text"] * s["body_repeat"]["count"]).encode("utf-8")
    else:
        body = s.get("body", "").encode("utf-8")
    lines = [s["method"] + " " + s["target"] + " HTTP/1.1", "Host: localhost"]
    lines += [name + ": " + value for name, value in s.get("headers", {}).items()]
    if body or s["method"] in ("POST", "PUT", "PATCH"):
        lines.append("Content-Length: " + str(len(body)))
    return ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body


def parse_responses(data, methods):
    """Split `data` into responses by Content-Length; a HEAD response carries no body bytes."""
    out, pos = [], 0
    while pos < len(data):
        end = data.find(b"\r\n\r\n", pos)
        if end < 0:
            raise AssertionError("incomplete response head: %r" % data[pos:])
        lines = data[pos:end].decode("latin-1").split("\r\n")
        status = int(re.match(r"HTTP/1\.1 (\d{3}) ", lines[0]).group(1))
        headers = {}
        for line in lines[1:]:
            name, _, value = line.partition(":")
            headers[name.lower()] = value.strip()
        length = int(headers["content-length"])
        head = len(out) < len(methods) and methods[len(out)] == "HEAD"
        start = end + 4
        body = b"" if head else data[start:start + length]
        out.append({"status": status, "headers": headers, "body": body, "length": length})
        pos = start if head else start + length
    return out


def check(test, label, response, expect):
    test.assertEqual(response["status"], expect["status"], label + ": status")
    for name, want in expect.get("headers", {}).items():
        if want is None:
            test.assertNotIn(name, response["headers"], label + ": header " + name + " must be absent")
        else:
            test.assertEqual(response["headers"].get(name), want, label + ": header " + name)
    test.assertNotIn("connection", response["headers"], label + ": no Connection header")
    if "body" in expect:
        test.assertEqual(response["body"].decode("utf-8"), expect["body"], label + ": body")


def replay(test, serve):
    """`serve(input_bytes) -> output_bytes` runs one fresh controller. Returns the number of checks made."""
    count = 0
    answered = [s for s in SUITE["stream"] if not s.get("unanswered")]
    out = serve(b"".join(request_bytes(s) for s in SUITE["stream"]))
    responses = parse_responses(out, [s["method"] for s in answered])
    test.assertEqual(len(responses), len(answered), "stream: one response per answered request, none after rest_stop()")
    for s, r in zip(answered, responses):
        check(test, s["name"], r, s["expect"])
        count += 1
    for s in SUITE["fatal"]:
        r = parse_responses(serve(request_bytes(s) + GOOD), [s["method"]])
        test.assertEqual(len(r), 1, s["name"] + ": one error response, then the end")
        check(test, s["name"], r[0], s["expect"])
        count += 1
    for s in SUITE["silent"]:
        test.assertEqual(serve(request_bytes(s)), b"", s["name"] + ": no output")
        count += 1
    return count


def new_controller(**options):
    registry = Registry()
    options.setdefault("max_body_bytes", SUITE["options"]["max_body_bytes"])
    options.setdefault("on_handler_error", lambda entry, message: None)
    rest = register_rest(registry, **options)
    program = load((DIR / "app.dslb").read_bytes(), (DIR / "host.schema.json").read_bytes(), registry)
    return registry, rest, program


def serve_in_memory(data, **options):
    sink = io.BytesIO()
    _, rest, program = new_controller(input=io.BytesIO(data), output=sink, **options)
    rest.run(program)
    return sink.getvalue()


def serve_process(data):
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8")
    command = [sys.executable, "-m", "lmcode.rest", str(DIR / "app.dslb"), str(DIR / "host.schema.json"),
               "--max-body-bytes", str(SUITE["options"]["max_body_bytes"])]
    done = subprocess.run(command, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(ROOT), env=env, timeout=60)
    if done.returncode != 0:
        raise AssertionError("lmcode.rest exited %d: %s" % (done.returncode, done.stderr.decode("utf-8", "replace")))
    return done.stdout
