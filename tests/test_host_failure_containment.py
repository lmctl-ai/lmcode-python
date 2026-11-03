import unittest
from unittest.mock import patch

from lmcode import Context, HostError, InvocationResults, Registry
from lmcode.loader import Entry, Program, Region
from lmcode.vm import _call_function, execute


class HostFailureContainmentTests(unittest.TestCase):
    def test_callback_allocation_failure_is_stable_run_host(self):
        registry = Registry(include_std=False)
        registry.function("allocate", [], "int", lambda *_: (_ for _ in ()).throw(MemoryError()))
        binding = next(iter(registry.functions.values()))
        with self.assertRaises(HostError) as raised:
            _call_function(binding, Context(), [], registry)
        self.assertEqual(raised.exception.code, "RUN_HOST")
        self.assertEqual(raised.exception.message, "memory allocation failed")

    def test_callback_recursion_failure_is_stable_run_host(self):
        registry = Registry(include_std=False)
        registry.function("recurse", [], "int", lambda *_: (_ for _ in ()).throw(RecursionError()))
        binding = next(iter(registry.functions.values()))
        with self.assertRaises(HostError) as raised:
            _call_function(binding, Context(), [], registry)
        self.assertEqual(raised.exception.code, "RUN_HOST")
        self.assertEqual(raised.exception.message, "maximum recursion depth exceeded")

    def test_vm_contains_native_allocation_and_recursion_failures(self):
        region = Region([], 0, bytes((0x32, 0, 0x11)), [])
        program = Program([], [], [], region, [], b"")
        registry = Registry(include_std=False)
        for native_error, expected in ((MemoryError(), "memory allocation failed"),
                                       (RecursionError(), "maximum recursion depth exceeded")):
            with self.subTest(error=type(native_error).__name__):
                with patch("lmcode.vm._math", side_effect=native_error):
                    with self.assertRaises(HostError) as raised:
                        execute(program, region, Context(), registry, [], False)
                self.assertEqual(raised.exception.code, "RUN_HOST")
                self.assertEqual(raised.exception.message, expected)

    def test_entry_argument_allocation_failure_is_run_host(self):
        region = Region([], 0, bytes((0x11,)), [])
        entry = Entry("main", "item", "", ("int",), "int", region)
        program = Program([], [], [], region, [entry], b"")

        class FailingArguments:
            def __len__(self):
                raise MemoryError()

        with self.assertRaises(HostError) as raised:
            program.call("main", Context(), Registry(include_std=False), FailingArguments())
        self.assertEqual((raised.exception.code, raised.exception.message),
                         ("RUN_HOST", "memory allocation failed"))

    def test_invocation_wraps_native_failures_in_terminal_frame(self):
        results = InvocationResults(False, False, ["/fixture"])
        results.fail(0, "run", MemoryError())
        frame = results.write_frame()
        self.assertEqual(frame["code"], 3)
        self.assertIn('"code":"RUN_HOST","message":"memory allocation failed"', frame["frame"])


if __name__ == "__main__":
    unittest.main()
