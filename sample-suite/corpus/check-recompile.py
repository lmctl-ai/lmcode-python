#!/usr/bin/env python3
"""Recompile pinned bytes, explicitly reporting unsupported released features."""
from pathlib import Path
import json
import os
import runpy
import shutil
import hashlib
import subprocess
import sys
import tempfile
suite = Path(__file__).resolve().parent
manifest = json.loads((suite / 'manifest.json').read_text())
runpy.run_path(str(suite / 'run-suite.py'))['check_files'](manifest)
compiler = shutil.which(os.environ.get('LMSCRIPT_BIN', 'lmscript'))
if not compiler:
    sys.exit('lmscript compiler unavailable')
excluded=set()
flagged=[]
with tempfile.TemporaryDirectory(prefix='sample-recompile-') as temporary:
    out = Path(temporary)
    args = [sys.executable, str(suite / 'compile.py'), '--output', str(out)]
    for feature in sorted(excluded):
        args += ['--exclude-feature', feature]
    subprocess.run(args, check=True)
    expected = [case for case in manifest['cases'] if not set(case.get('compiler_features', [])) & excluded]
    if {p.name for p in out.glob('*.dslb')} != {Path(case['bytecode']).name for case in expected}:
        sys.exit('compiler produced a different case set')
    for case in expected:
        source = suite / case['bytecode']
        if source.read_bytes() != (out / source.name).read_bytes():
            sys.exit('compiler bytecode drift: ' + source.name)
if excluded:
    print(f'SKIP {len(flagged)} literal source reproductions: verified v1 compiler lacks lmcode-literals-v1; use LMSCRIPT_BIN or LMCODE_REQUIRE_LITERAL_COMPILER=1')
print(f'PASS compiler reproduces {len(expected)}/{len(manifest["cases"])} pinned bytecode cases')
