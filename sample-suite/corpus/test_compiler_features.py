#!/usr/bin/env python3
"""Partial reproduction must never rewrite the canonical corpus."""
import hashlib
from pathlib import Path
import subprocess
import sys
import unittest
ROOT = Path(__file__).resolve().parent
class FeatureChecks(unittest.TestCase):
    def test_partial_cannot_write_canonical_output(self):
        before = hashlib.sha256((ROOT/'manifest.json').read_bytes()).digest()
        result = subprocess.run([sys.executable,str(ROOT/'compile.py'),'--exclude-feature','lmcode-literals-v1'],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('pinned manifest cannot be reduced',result.stderr)
        self.assertEqual(before,hashlib.sha256((ROOT/'manifest.json').read_bytes()).digest())
if __name__ == '__main__': unittest.main()
