"""WP186 regression tests for supported public behavior."""
import pathlib
import unittest
from unittest.mock import patch
from lmcode import Context, HostError, LoadError, Registry, ResultSink, load
from lmcode.loader import Entry, Program, Region

ROOT = pathlib.Path(__file__).resolve().parents[1]


class PublicErrorBoundaries(unittest.TestCase):
    def test_sink_recursive_values_are_structured_and_leave_previous_result(self):
        finite = []
        current = finite
        for _ in range(10000):
            child = []; current.append(child); current = child
        cycle = []; cycle.append(cycle)
        for value in (finite, cycle):
            for operation in ("set", "put"):
                with self.subTest(operation=operation, cyclic=value is cycle):
                    sink = ResultSink(); sink.put("kept", 7)
                    with self.assertRaisesRegex(HostError, "maximum recursion depth exceeded"):
                        sink.set(value) if operation == "set" else sink.put("bad", value)
                    self.assertEqual(sink.json(), '{"kept":7}')

    def test_sink_allocation_and_serialization_failures_are_structured(self):
        sink = ResultSink(); sink.set(7)
        with patch("lmcode.results.to_json_value", side_effect=MemoryError()):
            with self.assertRaisesRegex(HostError, "memory allocation failed"):
                sink.set(8)
        self.assertEqual(sink.json(), "7")
        with patch("lmcode.results._serialize_json", side_effect=RecursionError()):
            with self.assertRaisesRegex(HostError, "maximum recursion depth exceeded"):
                sink.json()

    def test_loader_native_failure_is_structured(self):
        vectors = ROOT / "conformance/vectors"
        raw = (vectors / "literals.dslb").read_bytes()
        schema = (vectors / "schema.json").read_bytes()
        with patch("lmcode.loader.Reader", side_effect=MemoryError()):
            with self.assertRaisesRegex(LoadError, "memory allocation failed") as caught:
                load(raw, schema, Registry(include_std=False))
        self.assertEqual(caught.exception.code, "LOAD_BAD_BYTECODE")

    def test_invalid_entry_indices_are_structured(self):
        region = Region([], 0, b"\x11", [])
        program = Program([], [], [], region, [Entry("ok", "", "", (), "void", region)], b"")
        for index in (-1, 1, 999):
            with self.subTest(index=index):
                with self.assertRaisesRegex(HostError, "not found"):
                    program.call(index, Context(), Registry(include_std=False), [])


if __name__ == "__main__":
    unittest.main()
