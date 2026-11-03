"""WP186 regression tests for supported public behavior."""
import unittest
from lmcode import Context, HostError, Registry
from lmcode.stdlib import _make_collection
from lmcode.vm import _call_method


class PriorityQueueRegressions(unittest.TestCase):
    def test_priority_ties_after_removing_items(self):
        registry = Registry()
        for owner, items in (("IntPQ", [1, 2, 3, 4, 5]),
                             ("FloatPQ", [1., 2., 3., 4., 5.]),
                             ("StrPQ", ["a", "b", "c", "d", "e"])):
            with self.subTest(owner=owner):
                queue = _make_collection(owner, [])
                def call(name, args):
                    binding = next(b for b in registry.methods.values() if b.owner == owner and b.name == name)
                    return _call_method(binding, Context(), queue, args, registry)
                for item in items[:4]:
                    call("push", [item, -0.0])
                call("pop", []); call("pop", [])
                call("push", [items[4], 0.0])
                self.assertEqual([call("pop", []) for _ in range(3)], items[2:])

    def test_priority_sequence_exhaustion_is_atomic_and_clear_resets(self):
        registry = Registry()
        for owner in ("IntPQ", "FloatPQ", "StrPQ"):
            with self.subTest(owner=owner):
                queue = _make_collection(owner, [])
                queue.value.next_sequence = (1 << 63) - 1
                def call(name, args):
                    binding = next(b for b in registry.methods.values() if b.owner == owner and b.name == name)
                    return _call_method(binding, Context(), queue, args, registry)
                item = "a" if owner == "StrPQ" else 1.0 if owner == "FloatPQ" else 1
                with self.assertRaisesRegex(HostError, "insertion sequence exhausted"):
                    call("push", [item, 0.0])
                self.assertEqual(queue.value.value, [])
                self.assertEqual(queue.value.next_sequence, (1 << 63) - 1)
                call("clear", [])
                self.assertEqual(queue.value.next_sequence, 0)
                call("push", [item, 0.0])
                self.assertEqual(queue.value.next_sequence, 1)
                with self.assertRaisesRegex(HostError, "priority must be finite"):
                    call("push", [item, float("nan")])
                self.assertEqual(queue.value.next_sequence, 1)


if __name__ == "__main__":
    unittest.main()
