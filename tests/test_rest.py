"""Unit and stdio tests for the opt-in `rest` std module (router, framing, registration, lifecycle, exchange rules)."""
import io
import json
import os
import queue
import threading
import unittest

import rest_replay as replay
from lmcode import HostError, LmcodeError, Registry
from lmcode.rest import Request, Response, RestController, RouteTable, parse_route, percent_decode, register_rest
from lmcode.rest.controller import Exchange
from lmcode.rest.http import body_length, encode_response, parse_head, take_request

HANDLER = "interface RestHandler(RestExchange) -> void"
SCHEMA = json.loads((replay.DIR / "host.schema.json").read_text(encoding="utf-8"))


class FakeEntry:
    def __init__(self, annotation, interface=HANDLER, name=None):
        self.annotation, self.interface, self.name = annotation, interface, name or annotation


class FakeProgram:
    def __init__(self, *entries):
        self.entries = [FakeEntry(*e) for e in entries]

    def run(self, context, registry):
        return None

    def call(self, *args):
        return None


def controller_with(program, **options):
    c = RestController(Registry(), **options)
    c.program = program
    return c


def get(target):
    return ("GET " + target + " HTTP/1.1\r\nHost: x\r\n\r\n").encode("latin-1")


class RouteTemplates(unittest.TestCase):
    def test_valid_shapes_parse_into_literal_param_and_rest_segments(self):
        route = parse_route("GET", "/users/{id}/files/{path...}")
        self.assertEqual([k for k, _ in route.segments], ["literal", "param", "literal", "rest"])
        self.assertEqual(len(parse_route("GET", "/").segments), 1)
        self.assertEqual(parse_route("GET", "/files/").segments[-1], ("literal", ""))

    def test_invalid_shapes_are_run_host_errors_with_pinned_text(self):
        def bad(method, path, pattern):
            with self.subTest(route=method + " " + path):
                with self.assertRaisesRegex(HostError, pattern) as raised:
                    parse_route(method, path)
                self.assertEqual(raised.exception.code, "RUN_HOST")
        bad("get", "/x", r"^rest: invalid route get /x: method must be one of GET, POST")
        bad("GET", "x", r"path must start with '/'")
        bad("GET", "/a b", "whitespace")
        bad("GET", "/a\x7fb", "control characters")
        bad("GET", "/a?b", r"whitespace, control characters, \? or #")
        bad("GET", "/a//b", "empty segment")
        bad("GET", "/{1x}", "invalid parameter name '1x'")
        bad("GET", "/{a}/{a}", "duplicate parameter 'a'")
        bad("GET", "/{a...}/x", "must be the last segment")
        bad("GET", "/a{b}", "malformed placeholder")
        bad("GET", "/{b", "malformed placeholder")

    def test_whitespace_is_ascii_only_so_utf8_bytes_are_ordinary(self):
        parse_route("GET", "/cafÃ ")  # C3 A0 as latin-1 characters
        parse_route("GET", "/ ")

    def test_duplicates_are_detected_by_shape_parameter_names_do_not_matter(self):
        table = RouteTable()
        table.add("GET", "/a/{x}", "one")
        table.add("POST", "/a/{x}", "two")
        with self.assertRaisesRegex(HostError, r"rest: duplicate route GET /a/\{y\}"):
            table.add("GET", "/a/{y}", "three")
        table.add("GET", "/a/b", "literal")

    def test_specificity_is_literal_then_param_then_rest_first_difference_wins(self):
        table = RouteTable()
        for path, name in (("/x/{rest...}", "rest"), ("/x/{p}/z", "param-z"), ("/x/{p}/{q}", "param-param"),
                           ("/x/y/{q}", "literal-param"), ("/x/y/z", "literal-literal")):
            table.add("GET", path, name)
        pick = lambda path: table.match("GET", path).route.annotation
        self.assertEqual(pick("/x/y/z"), "literal-literal")
        self.assertEqual(pick("/x/y/w"), "literal-param")
        self.assertEqual(pick("/x/a/z"), "param-z")
        self.assertEqual(pick("/x/a/b"), "param-param")
        self.assertEqual(pick("/x/a/b/c"), "rest")
        self.assertEqual(pick("/x/"), "rest")
        self.assertEqual(table.match("GET", "/x").status, 404)

    def test_404_vs_405_allow_header_and_head_fallback(self):
        table = RouteTable()
        table.add("GET", "/r", "g")
        table.add("DELETE", "/r", "d")
        table.add("PUT", "/only-put", "p")
        post = table.match("POST", "/r")
        self.assertEqual((post.status, post.allow), (405, "DELETE, GET, HEAD"))
        put = table.match("GET", "/only-put")
        self.assertEqual((put.status, put.allow), (405, "PUT"))
        self.assertEqual(table.match("GET", "/missing").status, 404)
        self.assertEqual(table.match("HEAD", "/r").route.method, "GET")
        self.assertEqual(table.match("HEAD", "/only-put").status, 405)

    def test_encoded_slashes_stay_in_one_segment_and_invalid_escapes_never_match(self):
        table = RouteTable()
        table.add("GET", "/f/{name}", "f")
        self.assertEqual(table.match("GET", "/f/a%2Fb").params["name"], "a/b")
        self.assertEqual(table.match("GET", "/f/a%2Fb/c").status, 404)
        self.assertEqual(table.match("GET", "/f/%zz").status, 404)
        self.assertEqual(table.match("GET", "/f/").status, 404, "an empty segment is not a {param}")

    def test_percent_decoding_yields_bytes_not_code_points(self):
        self.assertEqual(percent_decode("%C3%B6"), "Ã¶")
        self.assertEqual(percent_decode("a+b", True), "a b")
        self.assertEqual(percent_decode("a+b"), "a+b")
        self.assertIsNone(percent_decode("%4"))
        self.assertIsNone(percent_decode("%g1"))


class HttpSubset(unittest.TestCase):
    def test_request_heads(self):
        self.assertEqual(parse_head("GET /a?b=1 HTTP/1.1\r\nHost: x\r\nX-A: \t v \t"),
                         ("GET", "/a?b=1", [("Host", "x"), ("X-A", "v")]))
        self.assertEqual(parse_head("GET /a HTTP/1.0\r\nX:  v ")[2], [("X", " v ")], "only spaces and tabs are trimmed")
        for bad in ("garbage", "GET /a HTTP/2.0", "GET a HTTP/1.1", "GET /a#f HTTP/1.1", "get /a HTTP/1.1",
                    "GET /a HTTP/1.1\r\nNoColon", "GET /a HTTP/1.1\r\n: v", "GET /a HTTP/1.1\r\nBad Name: v",
                    "GET /a\x01b HTTP/1.1", "GET /a HTTP/1.1\r\nX: a\x01"):
            with self.subTest(head=bad):
                self.assertEqual(parse_head(bad), 400)

    def test_content_length_rules(self):
        self.assertEqual(body_length([]), (0, None))
        self.assertEqual(body_length([("content-length", "12")]), (12, None))
        self.assertEqual(body_length([("Content-Length", "1"), ("content-length", "1")]), (1, None))
        self.assertEqual(body_length([("Content-Length", "1"), ("content-length", "2")]), (None, 400))
        for value in ("-1", "1.5", "abc", "", "1" * 16, "١"):
            with self.subTest(value=value):
                self.assertEqual(body_length([("Content-Length", value)]), (None, 400))
        self.assertEqual(body_length([("Transfer-Encoding", "chunked")]), (None, 501))

    def test_response_encoding_has_no_connection_header(self):
        self.assertEqual(encode_response(Response(200, [("A", "b")], b"hi")), b"HTTP/1.1 200 OK\r\nA: b\r\nContent-Length: 2\r\n\r\nhi")
        self.assertEqual(encode_response(Response(299, [], b"hi"), head=True), b"HTTP/1.1 299 OK\r\nContent-Length: 2\r\n\r\n")

    def test_take_request_incremental_framing_fatal_errors_and_pipelined_remainders(self):
        full = b"POST /a HTTP/1.1\r\nContent-Length: 3\r\n\r\nabcGET /b HTTP/1.1\r\n\r\n"
        kind, (request, rest) = take_request(full, 1024)
        self.assertEqual((kind, request.body), ("request", b"abc"))
        self.assertEqual(take_request(rest, 1024)[1][0].target, "/b")
        self.assertEqual(take_request(b"GET /a HTT", 1024), ("need", None))
        self.assertEqual(take_request(b"POST /a HTTP/1.1\r\nContent-Length: 5\r\n\r\nab", 1024), ("need", None))
        self.assertEqual(take_request(b"POST /a HTTP/1.1\r\nContent-Length: 2000\r\n\r\n", 1024), ("fatal", 413))
        self.assertEqual(take_request(b"a" * 20000, 1024), ("fatal", 431))
        self.assertEqual(take_request(b"nonsense\r\n\r\n", 1024), ("fatal", 400))
        self.assertEqual(take_request(b"POST /a HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n", 1024), ("fatal", 501))


class Registration(unittest.TestCase):
    def test_exactly_the_18_declared_signatures_absent_from_the_default_registry(self):
        declared = sorted(
            ["fn %s(%s) -> %s" % (n, ", ".join(d["params"]), d["returns"]) for n, ds in SCHEMA["functions"].items() for d in ds]
            + ["method %s.%s(%s) -> %s" % (t, n, ", ".join(d["params"]), d["returns"])
               for t, td in SCHEMA["types"].items() for n, ds in td["methods"].items() for d in ds])
        self.assertEqual(len(declared), 18)
        plain = Registry()
        self.assertEqual(len(plain.signatures()), 206, "the default catalog is unchanged")
        self.assertEqual(len(plain.std_signatures), 206)
        self.assertFalse([s for s in plain.signatures() if "rest_" in s or "RestExchange" in s])
        register_rest(plain)
        self.assertEqual([s for s in plain.signatures() if "rest_" in s or "RestExchange" in s], declared)
        self.assertEqual(len(plain.signatures()), 224)
        self.assertEqual(len(plain.std_signatures), 206, "rest signatures are not part of the std catalog")

    def test_registering_twice_is_refused(self):
        registry = Registry()
        register_rest(registry)
        with self.assertRaises(LmcodeError) as raised:
            register_rest(registry)
        self.assertEqual(raised.exception.code, "LOAD_UNBOUND")


class ServeLifecycle(unittest.TestCase):
    def test_validation_errors_are_pinned_and_come_before_any_read(self):
        none = controller_with(FakeProgram())
        with self.assertRaisesRegex(HostError, "rest: no routes registered"):
            none.serve()
        missing = controller_with(FakeProgram())
        missing.route("GET", "/a", "nope")
        with self.assertRaisesRegex(HostError, r"rest: route GET /a references missing annotation @nope"):
            missing.serve()
        wrong = controller_with(FakeProgram(("a", "interface Rule(Node) -> void", "check")))
        wrong.route("GET", "/a", "a")
        with self.assertRaisesRegex(HostError, r"rest: entry check must implement RestHandler\(RestExchange\) -> void"):
            wrong.serve()
        dup = controller_with(FakeProgram(("a",), ("a",)))
        dup.route("GET", "/a", "a")
        with self.assertRaisesRegex(HostError, "rest: duplicate annotation @a"):
            dup.serve()
        unbound = RestController(Registry())
        unbound.route("GET", "/a", "a")
        with self.assertRaisesRegex(HostError, "rest: no program is bound"):
            unbound.serve()
        for c in (none, missing, wrong, dup):
            self.assertFalse(c.serving)

    def test_validation_order_is_already_called_then_unbound_then_routes(self):
        c = RestController(Registry())
        c.serving = True
        with self.assertRaisesRegex(HostError, "rest: rest_serve already called"):
            c.serve()
        c.serving = False
        with self.assertRaisesRegex(HostError, "rest: no program is bound"):
            c.serve()

    def test_entries_implementing_other_interfaces_are_ignored(self):
        c = controller_with(FakeProgram(("a",), ("other", "interface Rule(Node) -> void")))
        c.route("GET", "/a", "a")
        c.serve()
        self.assertTrue(c.serving)

    def test_routes_freeze_after_rest_serve_and_a_second_rest_serve_fails(self):
        c = controller_with(FakeProgram(("a",)))
        c.route("GET", "/a", "a")
        c.serve()
        with self.assertRaisesRegex(HostError, "rest: routes are frozen once rest_serve has been called"):
            c.route("GET", "/b", "a")
        with self.assertRaisesRegex(HostError, "rest: rest_serve already called"):
            c.serve()

    def test_a_stop_requested_by_the_body_means_nothing_is_read(self):
        class Unreadable(io.RawIOBase):
            def readinto(self, buffer):
                raise AssertionError("the input must not be read")
        class Body(FakeProgram):
            def run(self, context, registry):
                controller.route("GET", "/a", "a")
                controller.serve()
                controller.stop()
        controller = RestController(Registry(), input=Unreadable(), output=io.BytesIO())
        program = Body(("a",))
        controller.run(program)  # returns without touching the input

    def test_a_body_without_rest_serve_ends_and_reads_nothing(self):
        class Unreadable(io.RawIOBase):
            def readinto(self, buffer):
                raise AssertionError("the input must not be read")
        RestController(Registry(), input=Unreadable(), output=io.BytesIO()).run(FakeProgram())


class ExchangeRules(unittest.TestCase):
    def setUp(self):
        self.registry = Registry()
        self.controller = register_rest(self.registry)
        self.x = Exchange(self.controller, Request("GET", "/", [("X-Token", "a"), ("x-token", "b")]), {}, {}, "/")

    def call(self, signature, *args):
        return self.registry.methods["method RestExchange." + signature].callback(None, self.x, list(args))

    def test_status_must_be_200_to_599(self):
        with self.assertRaisesRegex(HostError, r"rest: status 199 out of range 200\.\.599"):
            self.call("status(int) -> void", 199)
        with self.assertRaisesRegex(HostError, "out of range"):
            self.call("status(int) -> void", 600)
        self.call("status(int) -> void", 599)
        self.assertEqual(self.x.status, 599)

    def test_header_names_and_values_are_validated(self):
        for name in ("", "a b", "a:b", "a\tb", "a\x7f"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(HostError, "invalid response header"):
                    self.call("set_header(string, string) -> void", name, "v")
        with self.assertRaisesRegex(HostError, "invalid response header"):
            self.call("set_header(string, string) -> void", "X", "a\r\nInjected: 1")
        self.call("set_header(string, string) -> void", "X- ", "ok")  # 0xA0 is an ordinary byte

    def test_reserved_headers_are_managed_by_the_server(self):
        for name in ("Content-Length", "connection", "TRANSFER-ENCODING"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(HostError, "managed by the server"):
                    self.call("set_header(string, string) -> void", name, "1")

    def test_same_header_name_replaces_case_insensitively(self):
        self.call("set_header(string, string) -> void", "X-A", "1")
        self.call("set_header(string, string) -> void", "x-a", "2")
        self.assertEqual(list(self.x.headers.values()), [("x-a", "2")])

    def test_request_headers_are_case_insensitive_and_repeated_ones_are_joined(self):
        self.assertEqual(self.call("header(string) -> string", "X-TOKEN"), "a, b")
        self.assertTrue(self.call("has_header(string) -> bool", "x-token"))
        self.assertFalse(self.call("has_header(string) -> bool", "nope"))
        self.assertEqual(self.call("header(string) -> string", "nope"), "")

    def test_counters_and_strings_are_separate_maps_and_counters_wrap_as_int64(self):
        self.assertEqual(self.call("increment(string) -> int", "k"), 1)
        self.assertEqual(self.call("increment(string) -> int", "k"), 2)
        self.assertEqual(self.call("get(string) -> string", "k"), "")
        self.call("set(string, string) -> void", "k", "v")
        self.assertEqual(self.call("get(string) -> string", "k"), "v")
        self.x.state["counts"]["big"] = 2 ** 63 - 1
        self.assertEqual(self.call("increment(string) -> int", "big"), -2 ** 63)


class Dispatch(unittest.TestCase):
    def setUp(self):
        _, self.rest, self.program = replay.new_controller(input=io.BytesIO(), output=io.BytesIO())
        self.rest.run(self.program)  # body registers the routes and rest_serve(); the empty input ends serving

    def test_dispatch_is_the_transport_independent_core(self):
        r = self.rest.dispatch(Request("GET", "/hello/w%C3%B6rld?greeting=hi+there", [], b""))
        self.assertEqual((r.status, r.body), (200, b"hi there, w\xc3\xb6rld"))
        self.assertEqual(r.headers, [("Content-Type", "text/plain; charset=utf-8")])

    def test_invalid_escapes_are_400_before_routing(self):
        for target in ("/nope?x=%zz", "/hello/%zz", "/nope%"):
            with self.subTest(target=target):
                r = self.rest.dispatch(Request("GET", target, [], b""))
                self.assertEqual((r.status, r.body), (400, b'{"error":"bad request"}'))

    def test_405_carries_allow_and_head_has_the_get_content_length(self):
        r = self.rest.dispatch(Request("POST", "/health", [], b""))
        self.assertEqual((r.status, dict(r.headers)["Allow"]), (405, "GET, HEAD"))
        self.assertEqual(encode_response(self.rest.dispatch(Request("HEAD", "/health", [], b"")), head=True).endswith(b"Content-Length: 15\r\n\r\n"), True)


class Stdio(unittest.TestCase):
    def test_conformance_suite_through_in_memory_streams(self):
        self.assertEqual(replay.replay(self, replay.serve_in_memory), 39)

    def test_conformance_suite_through_a_real_child_process_stdin_to_stdout(self):
        self.assertEqual(replay.replay(self, replay.serve_process), 39)

    def test_every_stream_scenario_composes_valid_http(self):
        for s in replay.SUITE["stream"]:
            with self.subTest(scenario=s["name"]):
                self.assertEqual(take_request(replay.request_bytes(s), 1 << 20)[0], "request")

    def test_pipelined_requests_in_one_chunk_are_answered_in_order(self):
        out = replay.serve_in_memory(get("/hello/a") + get("/hello/b") + get("/nope") + get("/hello/c"))
        self.assertEqual([r["status"] for r in replay.parse_responses(out, [])], [200, 200, 404, 200])

    def test_handler_errors_reach_on_handler_error_with_the_entry_name_and_never_the_client(self):
        seen = []
        out = replay.serve_in_memory(get("/boom") + get("/health"), on_handler_error=lambda entry, text: seen.append((entry, text)))
        a, b = replay.parse_responses(out, [])
        self.assertEqual((a["status"], a["body"]), (500, b'{"error":"internal error"}'))
        self.assertEqual(b["status"], 200)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0], "boom")
        self.assertRegex(seen[0][1], "zero")

    def test_invalid_percent_escapes_do_not_end_serving(self):
        out = replay.serve_in_memory(get("/nope?x=%zz") + get("/hello/%zz") + get("/health"))
        self.assertEqual([r["status"] for r in replay.parse_responses(out, [])], [400, 400, 200])

    def test_state_survives_across_requests_and_increment_counts_from_one(self):
        out = replay.serve_in_memory(get("/count") * 3)
        self.assertEqual([r["body"] for r in replay.parse_responses(out, [])], [b"1", b"2", b"3"])

    def test_requests_split_across_chunks_are_reassembled(self):
        class Trickle(io.RawIOBase):
            def __init__(self, parts):
                self.parts = list(parts)
            def readable(self):
                return True
            def readinto(self, buffer):
                if not self.parts:
                    return 0
                part = self.parts.pop(0)
                buffer[:len(part)] = part
                return len(part)
        body = '{"values":[10,20,12]}'
        parts = [b"POST /su", b"m HTTP/1.1\r\nHost: x\r\nContent-Len",
                 ("gth: %d\r\n\r\n{\"values\"" % len(body)).encode(), b":[10,20,12]}"]
        sink = io.BytesIO()
        _, rest, program = replay.new_controller(input=Trickle(parts), output=sink)
        rest.run(program)
        [r] = replay.parse_responses(sink.getvalue(), ["POST"])
        self.assertEqual((r["status"], r["body"]), (201, b'{"sum":42}'))

    def test_responses_stream_out_while_input_is_still_arriving(self):
        read_fd, write_fd = os.pipe()
        source = os.fdopen(read_fd, "rb")
        feed = os.fdopen(write_fd, "wb", buffering=0)
        lines = queue.Queue()
        class Sink:
            def write(self, data):
                lines.put(data)
            def flush(self):
                pass
        _, rest, program = replay.new_controller(input=source, output=Sink())
        worker = threading.Thread(target=rest.run, args=(program,))
        worker.start()
        try:
            feed.write(get("/count"))
            first = lines.get(timeout=20)
            feed.write(get("/count"))
            second = lines.get(timeout=20)
            self.assertEqual([r["body"] for r in replay.parse_responses(first + second, [])], [b"1", b"2"])
        finally:
            feed.close()
            worker.join(20)
            source.close()
        self.assertFalse(worker.is_alive(), "EOF on the input ends serving")

    def test_nothing_after_rest_stop_is_read_or_answered(self):
        out = replay.serve_in_memory(replay.request_bytes({"method": "POST", "target": "/shutdown"}) + get("/health"))
        [r] = replay.parse_responses(out, [])
        self.assertEqual((r["status"], r["body"]), (202, b"bye"))

    def test_the_serve_cli_reports_usage_and_load_errors_with_exit_codes(self):
        import subprocess, sys
        env = dict(os.environ, PYTHONPATH=str(replay.ROOT))
        def run(*args):
            return subprocess.run([sys.executable, "-m", "lmcode.rest", *args], input=b"", capture_output=True, env=env, cwd=str(replay.ROOT), timeout=60)
        self.assertEqual(run().returncode, 2)
        done = run("no-such-file.dslb", str(replay.DIR / "host.schema.json"))
        self.assertEqual(done.returncode, 3)
        self.assertEqual(done.stdout, b"")


if __name__ == "__main__":
    unittest.main()
