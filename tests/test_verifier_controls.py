import pathlib
import unittest

from lmcode import LoadError, load

ROOT = pathlib.Path(__file__).resolve().parents[1]
VECTORS = ROOT / "conformance" / "vectors"


class VerifierMutationControls(unittest.TestCase):
    def setUp(self):
        self.schema = (VECTORS / "schema.json").read_bytes()

    def rejects(self, name):
        bytecode = (VECTORS / (name + ".dslb")).read_bytes()
        with self.assertRaises(LoadError):
            load(bytecode, self.schema)

    def test_hidden_compiler_local_store_mutant_is_rejected(self):
        self.rejects("load-entry-hidden-store")

    def test_duplicate_entry_name_mutant_is_rejected(self):
        self.rejects("load-entry-dup-name")

    def test_entry_jump_out_mutant_is_rejected(self):
        schema = (VECTORS / "schema.json").read_bytes()
        bytecode = (VECTORS / "load-entry-jump-out.dslb").read_bytes()
        with self.assertRaises(LoadError):
            load(bytecode, schema)


if __name__ == "__main__":
    unittest.main()
