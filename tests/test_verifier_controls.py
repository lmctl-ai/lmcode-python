import json
import os
import pathlib
import unittest

from lmcode import LoadError, Registry, load
from lmcode.loader import Program, Region, _decode, _verify_stack

ROOT = pathlib.Path(os.environ.get("LMCODE_TEST_ROOT", pathlib.Path(__file__).resolve().parents[1]))
VECTORS = ROOT / "conformance" / "vectors"


class VerifierMutationControls(unittest.TestCase):
    def setUp(self):
        self.schema = (VECTORS / "schema.json").read_bytes()
        document = json.loads(self.schema)
        self.registry = Registry(include_std=False)
        for name, declarations in document.get("functions", {}).items():
            for declaration in declarations:
                self.registry.function(name, declaration.get("params", []), declaration.get("returns", "void"), lambda ctx, self, args: None)
        for owner, definition in document.get("types", {}).items():
            for name, declarations in definition.get("methods", {}).items():
                for declaration in declarations:
                    self.registry.method(owner, name, declaration.get("params", []), declaration.get("returns", "void"), lambda ctx, self, args: None)
        for name, type_name in document.get("context", {}).items():
            self.registry.context(name, type_name)

    def rejects(self, name):
        bytecode = (VECTORS / (name + ".dslb")).read_bytes()
        with self.assertRaises(LoadError):
            load(bytecode, self.schema, self.registry)

    def test_valid_bytecode_is_accepted(self):
        bytecode = (VECTORS / "literals.dslb").read_bytes()
        self.assertTrue(load(bytecode, self.schema, self.registry).body.code)

    def test_hidden_compiler_local_store_mutant_is_rejected(self):
        self.rejects("load-entry-hidden-store")

    def test_duplicate_entry_name_mutant_is_rejected(self):
        self.rejects("load-entry-dup-name")

    def test_entry_jump_out_mutant_is_rejected(self):
        bytecode = (VECTORS / "load-entry-jump-out.dslb").read_bytes()
        with self.assertRaisesRegex(LoadError, "jump"):
            load(bytecode, self.schema, self.registry)

    def test_ordinary_backward_jump_is_rejected(self):
        bytecode = (VECTORS / "load-backward-jump.dslb").read_bytes()
        with self.assertRaisesRegex(LoadError, "goes backwards"):
            load(bytecode, self.schema, self.registry)

    def test_branch_join_depth_mismatch_is_rejected(self):
        # A typed void entry joins HALT with zero values on one path, one on the other.
        code = bytes([0x03, 1, 0x0D]) + (9).to_bytes(4, "big", signed=True)
        code += bytes([0x01]) + (1).to_bytes(8, "big", signed=True) + bytes([0x11])
        program = Program([], [], [], None, [], b"")
        region = Region([], 1, code, [])
        _decode(region, [], 0, 0)
        with self.assertRaisesRegex(LoadError, "inconsistent operand stack depth"):
            _verify_stack(program, self.registry, region, "void")

    def test_stack_underflow_is_rejected(self):
        program = Program([], [], [], None, [], b"")
        region = Region([], 0, bytes([0x10, 0x11]), [])
        _decode(region, [], 0, 0)
        with self.assertRaisesRegex(LoadError, "operand stack underflow"):
            _verify_stack(program, self.registry, region, "void")


if __name__ == "__main__":
    unittest.main()
