#!/usr/bin/env python3
"""Run pinned bytes and diff exact stdout + exit. No expectations are inferred."""
import difflib
import hashlib
import json
import os
import runpy
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent


def check_files(manifest):
    if not manifest.get('cases'):
        raise ValueError('empty manifest cannot pass')
    if len({case['name'] for case in manifest['cases']}) != len(manifest['cases']):
        raise ValueError('duplicate case names')
    def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
    if digest(ROOT / manifest['schema']) != manifest['schema_sha256']:
        raise ValueError('schema changed: recompile and review expectations')
    for case in manifest['cases']:
        if digest(ROOT / case['bytecode']) != case['bytecode_sha256']:
            raise ValueError(case['name'] + ': stale/corrupt bytecode')
        if 'source' in case and digest(ROOT / case['source']) != case['source_sha256']:
            raise ValueError(case['name'] + ': source changed without recompilation')


def prepare_tmp(directory):
    for name, value in json.loads((ROOT / 'manifest.json').read_text()).get('fixtures', {}).items():
        if Path(name).name != name:
            raise ValueError('unsafe fixture name')
        (Path(directory) / name).write_bytes(bytes.fromhex(value))


def check_compiler():
    runpy.run_path(str(ROOT / 'check-compile-errors.py'))['check']()


def run(command, bytecode, timeout=30):
    with tempfile.TemporaryDirectory(prefix='lmcode-sample-') as scratch:
        prepare_tmp(scratch)
        env = dict(os.environ, SAMPLE_TMP=str(Path(scratch).resolve()))
        return subprocess.run([*command, '--lmcode', str(bytecode.resolve())], env=env, capture_output=True, timeout=timeout)


def main():
    command = sys.argv[1:]
    if not command:
        sys.exit('usage: run-suite.sh EXECUTABLE [COMMAND_ARGUMENT ...]')
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    check_files(manifest)
    check_compiler()
    runpy.run_path(str(ROOT / 'protocol.py'))['check'](command)
    failed = 0
    for case in manifest['cases']:
        name = case['name']
        expected = (ROOT / 'expected' / (name + '.out')).read_bytes()
        code = int((ROOT / 'expected' / (name + '.exit')).read_text())
        if code != case['expected_exit']:
            raise ValueError(name + ': exit fixture contradicts manifest intent')
        result = run(command, ROOT / case['bytecode'], case.get('timeout_seconds', 30))
        runpy.run_path(str(ROOT / 'return_protocol.py'))['validate'](result.stdout, result.returncode, case.get('expected_return'))
        good = result.returncode == code and result.stdout == expected and not result.stderr
        print(('PASS ' if good else 'FAIL ') + name)
        if not good:
            failed += 1
            print(f'  exit: expected {code}, got {result.returncode}; stderr={result.stderr.decode(errors="replace")!r}')
            print(''.join(difflib.unified_diff(expected.decode(errors='replace').splitlines(True),
                                            result.stdout.decode(errors='replace').splitlines(True),
                                            fromfile='expected', tofile='actual')), end='')
    print(f'PASS {len(manifest["cases"])}/{len(manifest["cases"])} sample cases' if not failed
          else f'FAIL {failed}/{len(manifest["cases"])} sample cases')
    return 1 if failed else 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        sys.exit('suite error: ' + str(error))
