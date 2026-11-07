"""The `rest` std module: registration, the transport-independent dispatcher and the stdio pump (spec/std-rest.md)."""
from __future__ import annotations
import re
import sys
from typing import Any, Callable, Dict, List, Optional
from ..errors import HostError
from ..registry import Context, ObjectRef, Registry
from .http import Request, Response, ascii_lower, encode_response, error_response, take_request
from .router import RouteTable, percent_decode

HANDLER_INTERFACE = "interface RestHandler(RestExchange) -> void"
_RESERVED = {"content-length", "connection", "transfer-encoding"}
_BAD_HEADER_NAME = re.compile(r"[\x00-\x20\x7f:]")
_CHUNK = 64 * 1024


def _wrap64(value: int) -> int:
    value &= (1 << 64) - 1
    return value - (1 << 64) if value & (1 << 63) else value


def _default_on_error(entry: str, message: str) -> None:
    sys.stderr.write("rest: handler " + entry + " failed: " + message + "\n")
    sys.stderr.flush()


class Exchange:
    """Per-request state behind a RestExchange object."""

    def __init__(self, controller: "RestController", request: Request, params, query, path):
        self.state = controller.state
        self.request = request
        self.body_text = request.body.decode("latin-1")
        self.params, self.query, self.path = params, query, path
        self.status = 200
        self.headers: Dict[str, Any] = {}
        self.body = ""

    def request_header(self, name: str) -> List[str]:
        wanted = ascii_lower(name)
        return [v for n, v in self.request.headers if ascii_lower(n) == wanted]


class RestController:
    def __init__(self, registry: Registry, input=None, output=None, max_body_bytes: int = 1024 * 1024,
                 on_handler_error: Optional[Callable[[str, str], None]] = None):
        self.registry = registry
        self.input = input
        self.output = output
        self.max_body_bytes = max_body_bytes
        self.on_handler_error = on_handler_error or _default_on_error
        self.state = {"values": {}, "counts": {}}
        self.table = RouteTable()
        self.program = None
        self.context: Optional[Context] = None
        self.entry_index: Dict[str, Any] = {}
        self.serving = False
        self.stopped = False

    # ---- host-facing -------------------------------------------------------------------------------------
    def run(self, program, context: Optional[Context] = None):
        """Bind `program`, run its body, then (if it called rest_serve and not rest_stop) serve until EOF, rest_stop() or a framing error."""
        self.program = program
        self.context = context if context is not None else Context()
        self.stopped = False
        result = program.run(self.context, self.registry)
        if self.serving and not self.stopped:
            self._pump()
        return result

    def stop(self) -> None:
        """End serving once the current response is written."""
        self.stopped = True

    # ---- lmcode-facing -----------------------------------------------------------------------------------
    def route(self, method: str, path: str, annotation: str) -> None:
        if self.serving:
            raise HostError("rest: routes are frozen once rest_serve has been called")
        self.table.add(method, path, annotation)

    def serve(self) -> None:
        if self.serving:
            raise HostError("rest: rest_serve already called")
        if self.program is None:
            raise HostError("rest: no program is bound (run the program through the controller)")
        self._bind()
        self.serving = True

    def _bind(self) -> None:
        if not self.table.size:
            raise HostError("rest: no routes registered")
        index: Dict[str, Any] = {}
        for i, entry in enumerate(self.program.entries):
            if entry.interface != HANDLER_INTERFACE:
                continue
            if entry.annotation in index:
                raise HostError("rest: duplicate annotation @" + entry.annotation)
            index[entry.annotation] = (i, entry.name)
        self.entry_index = index
        for route in self.table.routes:
            if route.annotation in index:
                continue
            wrong = next((e for e in self.program.entries if e.annotation == route.annotation), None)
            if wrong is not None:
                raise HostError("rest: entry " + wrong.name + " must implement RestHandler(RestExchange) -> void")
            raise HostError("rest: route " + route.method + " " + route.path + " references missing annotation @" + route.annotation)

    # ---- the transport-independent core ------------------------------------------------------------------
    def dispatch(self, request: Request) -> Response:
        """Request(method, target, headers [(name, value)], body bytes) -> Response(status, headers, body bytes)."""
        mark = request.target.find("?")
        raw_path = request.target if mark < 0 else request.target[:mark]
        query_text = "" if mark < 0 else request.target[mark + 1:]
        path = percent_decode(raw_path)
        if path is None:
            return error_response(400)
        query: Dict[str, str] = {}
        if query_text:
            for pair in query_text.split("&"):
                if pair == "":
                    continue
                eq = pair.find("=")
                key = percent_decode(pair if eq < 0 else pair[:eq], True)
                value = percent_decode("" if eq < 0 else pair[eq + 1:], True)
                if key is None or value is None:
                    return error_response(400)
                query.setdefault(key, value)
        match = self.table.match(request.method, raw_path)
        if match.status == 404:
            return error_response(404)
        if match.status == 405:
            return error_response(405, [("Allow", match.allow)])
        index, name = self.entry_index[match.route.annotation]
        exchange = Exchange(self, request, match.params, query, path)
        try:
            self.program.call(index, self.context, self.registry, [ObjectRef("RestExchange", exchange, id(exchange))])
        except Exception as error:  # any run-time error becomes a 500; the message only reaches the host callback
            try:
                self.on_handler_error(name, str(error))
            except Exception:
                pass
            return error_response(500)
        return self._response(exchange)

    @staticmethod
    def _response(x: Exchange) -> Response:
        headers = [(n, v) for n, v in x.headers.values()]
        body = x.body.encode("latin-1")
        if x.status in (204, 304):
            body = b""
        elif body and "content-type" not in x.headers:
            headers.insert(0, ("Content-Type", "text/plain; charset=utf-8"))
        return Response(x.status, headers, body)

    # ---- the stdio pump ----------------------------------------------------------------------------------
    def _pump(self) -> None:
        source = self.input if self.input is not None else sys.stdin.buffer
        sink = self.output if self.output is not None else sys.stdout.buffer
        read = getattr(source, "read1", None) or source.read

        def write(response: Response, head: bool) -> None:
            sink.write(encode_response(response, head))
            sink.flush()

        buffer = b""
        while True:
            chunk = read(_CHUNK)
            if not chunk:
                return
            buffer += chunk
            while True:
                kind, value = take_request(buffer, self.max_body_bytes)
                if kind == "need":
                    break
                if kind == "fatal":
                    write(error_response(value), False)
                    return
                request, buffer = value
                write(self.dispatch(request), request.method == "HEAD")
                if self.stopped:
                    return


def register_rest(registry: Registry, input=None, output=None, max_body_bytes: int = 1024 * 1024,
                  on_handler_error: Optional[Callable[[str, str], None]] = None) -> RestController:
    """Register the 18 `rest` signatures in `registry` and return the controller that owns serving. Opt-in: never called by Registry()."""
    controller = RestController(registry, input, output, max_body_bytes, on_handler_error)

    def fn(name, params, returns, callback):
        registry.function(name, params, returns, lambda ctx, receiver, args: callback(*args), raw_strings=True)

    def method(name, params, returns, callback):
        registry.method("RestExchange", name, params, returns, lambda ctx, receiver, args: callback(receiver, *args), raw_strings=True)

    fn("rest_route", ["string", "string", "string"], "void", controller.route)
    fn("rest_serve", [], "void", controller.serve)
    fn("rest_stop", [], "void", controller.stop)

    method("method", [], "string", lambda x: x.request.method)
    method("path", [], "string", lambda x: x.path)
    method("query", ["string"], "string", lambda x, key: x.query.get(key, ""))
    method("has_query", ["string"], "bool", lambda x, key: key in x.query)
    method("param", ["string"], "string", lambda x, name: x.params.get(name, ""))
    method("header", ["string"], "string", lambda x, name: ", ".join(x.request_header(name)))
    method("has_header", ["string"], "bool", lambda x, name: bool(x.request_header(name)))
    method("body", [], "string", lambda x: x.body_text)

    def status(x, code):
        if code < 200 or code > 599:
            raise HostError("rest: status " + str(code) + " out of range 200..599")
        x.status = code

    def set_header(x, name, value):
        if name == "" or _BAD_HEADER_NAME.search(name) or "\r" in value or "\n" in value:
            raise HostError("rest: invalid response header")
        key = ascii_lower(name)
        if key in _RESERVED:
            raise HostError("rest: response header " + name + " is managed by the server")
        x.headers[key] = (name, value)

    def send(x, body):
        x.body = body

    def json(x, body):
        x.body = body
        x.headers["content-type"] = ("Content-Type", "application/json")

    def set_value(x, key, value):
        x.state["values"][key] = value

    def increment(x, key):
        counts = x.state["counts"]
        counts[key] = _wrap64(counts.get(key, 0) + 1)
        return counts[key]

    method("status", ["int"], "void", status)
    method("set_header", ["string", "string"], "void", set_header)
    method("send", ["string"], "void", send)
    method("json", ["string"], "void", json)
    method("get", ["string"], "string", lambda x, key: x.state["values"].get(key, ""))
    method("set", ["string", "string"], "void", set_value)
    method("increment", ["string"], "int", increment)
    return controller
