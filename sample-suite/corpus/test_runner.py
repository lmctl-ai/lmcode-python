#!/usr/bin/env python3
"""Negative controls for the pinned sample runner and schema audit."""

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent

FAKE_HOST = r'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import runpy
import sys

sys.stdout.reconfigure(newline="\n")
def failure(v):
 print("LMCODE_RETURN_BEGIN");print(json.dumps(v));print("LMCODE_RETURN_END")
root = Path(os.environ["FAKE_SUITE"])
mode = os.environ.get("FAKE_MODE", "ok")
args = sys.argv[1:]
if os.environ.get("EXEC_MARKER") and args[:1] == ["--lmcode"] and len(args) == 2 and Path(args[1]).exists():
    Path(os.environ["EXEC_MARKER"]).write_text("ran")

if args == ["--version"]:
    if mode == "bad-cli":
        print("lmcode-fake-sample 0.1.0")
        raise SystemExit(1)
    print("lmcode-fake-sample 0.1.0")
    raise SystemExit(0)
if args[:1] == ["--lmcode-schema"]:
    if len(args) > 2 or (len(args) == 2 and args[1] != "--json"):
        failure({"ok": False, "phase": "cli", "code": "CLI_USAGE", "message": "usage: --version | --lmcode-schema [--json] | --lmcode-signatures | --lmcode FILE"})
        raise SystemExit(2)
    print((root / "sample.dsl.json").read_text(), end="")
    raise SystemExit(0)
if args == ["--lmcode-signatures"]:
    fn = runpy.run_path(str(root / "protocol.py"))["declared_signatures"]
    sys.stdout.buffer.write(fn(json.loads((root / "sample.dsl.json").read_text())))
    raise SystemExit(0)
if not args or args[0] == "--unknown" or (args[0] == "--lmcode" and len(args) != 2):
    failure({"ok": False, "phase": "cli", "code": "CLI_USAGE", "message": "usage: --version | --lmcode-schema [--json] | --lmcode-signatures | --lmcode FILE"})
    raise SystemExit(2)
if args[0] == "--lmcode" and len(args) == 2:
    path = Path(args[1])
    if not path.exists():
        failure({"ok": False, "phase": "app", "code": "APP_FAIL", "message": "invalid sample bytecode"})
        raise SystemExit(4)
    stem = path.stem
    expected = root / "expected" / (stem + ".out")
    code = int((root / "expected" / (stem + ".exit")).read_text())
    output = expected.read_bytes()
    if mode == "wrong-output" and output:
        output = output[:-1] + b"X\n"
    if mode == "whitespace" and output:
        output = output.rstrip(b"\n") + b" \n"
    sys.stdout.buffer.write(output)
    if mode == "stderr":
        sys.stderr.write("unexpected host stderr\n")
    raise SystemExit(code + 1 if mode == "wrong-exit" else code)
failure({"ok": False, "phase": "cli", "code": "CLI_USAGE", "message": "usage: --version | --lmcode-schema [--json] | --lmcode-signatures | --lmcode FILE"})
raise SystemExit(2)
'''


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sample-runner-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.suite = self.tmp / "suite"
        shutil.copytree(ROOT, self.suite)
        host_dir = self.tmp / "host dir with spaces"
        host_dir.mkdir()
        self.host = host_dir / "fake host.py"
        self.host.write_text(FAKE_HOST)
        self.host.chmod(self.host.stat().st_mode | stat.S_IXUSR)
        self.env = dict(os.environ, FAKE_SUITE=str(self.suite))

    def run_suite(self, mode=None):
        env = dict(self.env)
        if mode:
            env["FAKE_MODE"] = mode
        return subprocess.run(
            [sys.executable, str(self.suite / "run-suite.py"), sys.executable, str(self.host)],
            env=env, text=True, capture_output=True, timeout=30,
        )

    def test_positive_fixture_host_passes(self):
        result = self.run_suite()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS", result.stdout)

    def test_wrong_exit_fails_exact_runner(self):
        self.assertNotEqual(self.run_suite("wrong-exit").returncode, 0)

    def test_json_whitespace_mutation_fails_exact_runner(self):
        self.assertNotEqual(self.run_suite("whitespace").returncode, 0)

    def test_stderr_output_fails_even_when_stdout_matches(self):
        self.assertNotEqual(self.run_suite("stderr").returncode, 0)

    def test_bytecode_hash_mutation_fails_before_host_execution(self):
        target = next(self.suite.glob("bytecode/*.dslb"))
        original = target.read_bytes()
        target.write_bytes(bytes([original[0] ^ 1]) + original[1:])
        marker = self.tmp / "executed"
        env = dict(self.env, EXEC_MARKER=str(marker))
        result = subprocess.run([sys.executable, str(self.suite / "run-suite.py"), str(self.host)], env=env, text=True, capture_output=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(marker.exists())

    def test_source_change_without_recompile_fails_before_host_execution(self):
        source = next(self.suite.glob("programs/*.lms"))
        source.write_text(source.read_text() + "\n")
        self.assertNotEqual(self.run_suite().returncode, 0)

    def test_audit_rejects_added_standard_signature_without_coverage(self):
        # The control is portable when the corpus is vendored into any sample.
        schema = {"functions": {}, "types": {}}
        schema["functions"]["test_new_signature"] = [{"params": [], "returns": "void"}]
        mutated = self.tmp / "std-mutated.json"
        mutated.write_text(json.dumps(schema))
        result = subprocess.run([sys.executable, str(self.suite / "audit.py"), "--std", str(mutated)], env=self.env, text=True, capture_output=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("UNEXERCISED", result.stderr + result.stdout)

    def test_bad_cli_status_is_rejected_by_protocol(self):
        result = self.run_suite("bad-cli")
        self.assertNotEqual(result.returncode, 0)

    def test_empty_manifest_cannot_report_false_pass(self):
        manifest = json.loads((self.suite / "manifest.json").read_text())
        manifest["cases"] = []
        (self.suite / "manifest.json").write_text(json.dumps(manifest))
        result = self.run_suite()
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
