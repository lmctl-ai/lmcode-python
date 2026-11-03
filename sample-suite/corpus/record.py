#!/usr/bin/env python3
"""Explicit maintainer operation: derive expectations only from the C++ reference."""
import json
from pathlib import Path
import subprocess
import sys
import runpy
ROOT = Path(__file__).resolve().parent
runner = runpy.run_path(str(ROOT / 'run-suite.py'))
validate = runpy.run_path(str(ROOT / 'return_protocol.py'))['validate']
command = sys.argv[1:]
if not command or not subprocess.check_output([*command, '--version']).startswith(b'lmcode-cpp-sample '):
    sys.exit('record.py requires the C++ reference executable')
manifest = json.loads((ROOT / 'manifest.json').read_text())
runner['check_files'](manifest)
for case in manifest['cases']:
    result = runner['run'](command, ROOT / case['bytecode'], case.get('timeout_seconds', 30))
    if result.stderr or result.returncode != case['expected_exit']:
        sys.exit(f'{case["name"]}: reference crashed or wrote stderr: {result.stderr!r}')
    lines = result.stdout.splitlines()
    validate(result.stdout, result.returncode, case.get('expected_return'))
    result_line = json.loads(lines[-2])
    if result_line.get('ok') != (result.returncode == 0):
        sys.exit(case['name'] + ': inconsistent JSON/exit')
    (ROOT / 'expected' / (case['name'] + '.out')).write_bytes(result.stdout)
    (ROOT / 'expected' / (case['name'] + '.exit')).write_text(str(result.returncode) + '\n', newline='\n')
print(f'Recorded {len(manifest["cases"])} C++ reference expectations; REVIEW THE DIFF')
