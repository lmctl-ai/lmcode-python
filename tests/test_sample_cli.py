import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class SampleCliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "sample.main", *args], cwd=ROOT,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_version_and_exact_schema_bytes(self):
        version = self.run_cli("--version")
        self.assertEqual(version.returncode, 0)
        self.assertEqual(version.stdout, b"lmcode-python-sample 0.1.0\n")
        schema = self.run_cli("--lmcode-schema")
        self.assertEqual(schema.returncode, 0)
        self.assertEqual(schema.stdout, (ROOT / "sample/data/sample.dsl.json").read_bytes())

    def test_bad_cli_arguments_get_one_terminal_frame(self):
        result = self.run_cli("--unknown")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, b"")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[0], b"LMCODE_RETURN_BEGIN")
        self.assertEqual(lines[-1], b"LMCODE_RETURN_END")
        envelope = json.loads(lines[1])
        self.assertEqual((envelope["ok"], envelope["phase"], envelope["code"]), (False, "cli", "CLI_USAGE"))


if __name__ == "__main__":
    unittest.main()
