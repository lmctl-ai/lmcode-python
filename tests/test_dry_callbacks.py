import pathlib
import tempfile
import unittest

from lmcode import Context, Registry, dry, load
from lmcode.results import ResultContract, ResultSink

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "conformance" / "invocation-vectors"
SCHEMA = (FIXTURES / "schema.json").read_bytes()
BYTECODE = (FIXTURES / "a.dslb").read_bytes()


class DryCallbackTests(unittest.TestCase):
    def execute(self, dry_mode, callback, dry_callback=None, sentinel=None):
        registry = Registry()
        calls = {"real": 0, "dry": 0}

        def real_call(context, receiver, args):
            calls["real"] += 1
            if sentinel is not None:
                sentinel.write_text("real callback ran", encoding="utf-8")
            return 41

        def preview_call(context, receiver, args):
            calls["dry"] += 1
            return 7

        registry.function("next_counter", [], "int", real_call,
                          dry(preview_call) if dry_callback else None)
        program = load(BYTECODE, SCHEMA, registry)
        sink = ResultSink(ResultContract())
        registry.set_result_sink(sink)
        context = Context()
        context.dry_mode = dry_mode
        context.result_sink = sink
        program.run(context, registry)
        return calls, sink.json()

    def test_default_dry_skips_effectful_real_callback(self):
        with tempfile.TemporaryDirectory(prefix="lmcode-python-dry-") as directory:
            sentinel = pathlib.Path(directory) / "real-sentinel"
            calls, payload = self.execute(True, None, False, sentinel)
            self.assertFalse(sentinel.exists())
            self.assertEqual(calls, {"real": 0, "dry": 0})
            self.assertEqual(payload, '{"id":"A","counter":0}')

    def test_dry_override_runs_once_without_running_real_callback(self):
        calls, payload = self.execute(True, None, True)
        self.assertEqual(calls, {"real": 0, "dry": 1})
        self.assertEqual(payload, '{"id":"A","counter":7}')

    def test_real_mode_keeps_real_callback_unchanged(self):
        with tempfile.TemporaryDirectory(prefix="lmcode-python-real-") as directory:
            sentinel = pathlib.Path(directory) / "real-sentinel"
            calls, payload = self.execute(False, None, True, sentinel)
            self.assertTrue(sentinel.exists())
            self.assertEqual(calls, {"real": 1, "dry": 0})
            self.assertEqual(payload, '{"id":"A","counter":41}')


    def test_skipped_collection_callbacks_return_fresh_dummies(self):
        from lmcode.vm import _call_function
        registry = Registry()
        calls = []
        registry.function("fresh_list", [], "IntList",
                          lambda context, receiver, args: calls.append("real"))
        binding = registry.functions["fn fresh_list() -> IntList"]
        context = Context(dry_mode=True)
        first = _call_function(binding, context, [], registry)
        second = _call_function(binding, context, [], registry)
        first.value.value.append(1)
        self.assertEqual(second.value.value, [])
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
