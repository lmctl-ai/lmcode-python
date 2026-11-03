"""WP186 regression tests for supported public behavior."""
import unittest
from lmcode import Context, Registry
from lmcode.vm import _call_function, _call_method


class RawStringsRegistration(unittest.TestCase):
    def test_documented_raw_strings_keyword(self):
        registry = Registry(include_std=False)
        registry.function("raw", ["string"], "string", lambda c, r, a: a[0], raw_strings=True)
        registry.method("Thing", "raw", ["string"], "string", lambda c, r, a: a[0], raw_strings=True)
        value = "\xff\x00"
        binding = registry.functions['fn raw(string) -> string']
        self.assertEqual(_call_function(binding, Context(), [value], registry), value)
        from lmcode.registry import ObjectRef
        binding = registry.methods['method Thing.raw(string) -> string']
        self.assertEqual(_call_method(binding, Context(), ObjectRef("Thing", object()), [value], registry), value)


if __name__ == "__main__":
    unittest.main()
