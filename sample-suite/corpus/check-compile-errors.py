#!/usr/bin/env python3
"""Compile-only language features: recursion is rejected, not silently emulated."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import re
ROOT = Path(__file__).resolve().parent

def check():
    compiler = shutil.which(os.environ.get('LMSCRIPT_BIN', 'lmscript'))
    if not compiler:
        raise ValueError('lmscript is required for compile-rejection cases')
    cases = json.loads((ROOT / 'compile-errors/manifest.json').read_text())['cases']
    for case in cases:
        with tempfile.TemporaryDirectory(prefix='sample-compile-error-') as work:
            output = Path(work) / 'must-not-exist.dslb'
            result = subprocess.run(['node',str(ROOT/'compile-fixture.mjs'),str(ROOT/'compile-errors'/case['source']),str(output)], capture_output=True, timeout=30)
            location = ''
            if 'line' in case:
                location = ':' + str(case['line']) + ':' + str(case['column']) + ':'
            diagnostic_ok = case['diagnostic'].encode() in result.stderr
            location_ok = not location or re.search(re.escape(location), result.stderr.decode(errors='replace')) is not None
            if result.returncode != case['exit'] or not diagnostic_ok or not location_ok or output.exists():
                raise ValueError('compiler rejection mismatch: ' + case['source'] + ': ' + result.stderr.decode(errors='replace'))
    print(f'PASS {len(cases)} compiler rejection case(s), exit 2')

if __name__ == '__main__':
    try:
        check()
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        sys.exit(str(error))
