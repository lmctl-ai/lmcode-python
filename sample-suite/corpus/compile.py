#!/usr/bin/env python3
"""Compile source wrappers; expectations are never rewritten here."""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'bytecode')
    parser.add_argument('--exclude-feature', action='append', default=[], help='explicit partial reproducibility check; requires --output')
    args = parser.parse_args()
    if args.exclude_feature and args.output.resolve() == (ROOT / 'bytecode').resolve():
        parser.error('partial compilation requires a separate --output; pinned manifest cannot be reduced')
    args.output.mkdir(parents=True, exist_ok=True)
    coverage = json.loads((ROOT / 'coverage.json').read_text())
    known_features = {feature for features in coverage.get('compiler_features', {}).values() for feature in features}
    if set(args.exclude_feature) - known_features:
        parser.error('unknown compiler feature')
    compiler_name = os.environ.get('LMSCRIPT_BIN', 'lmscript')
    compiler = shutil.which(compiler_name)
    if not compiler:
        sys.exit('compiler not found: ' + compiler_name)
    cases = []
    for source in sorted((ROOT / 'programs').glob('*.lms')):
        if len(source.read_text().splitlines()) > 40:
            sys.exit(f'{source.name}: exceeds 40 lines')
        required = coverage.get('compiler_features', {}).get(source.name, [])
        if set(required) & set(args.exclude_feature):
            print('SKIP compiler reproduction: ' + source.name + ' requires ' + ','.join(required))
            continue
        output = args.output / (source.stem + '.dslb')
        subprocess.run(['node',str(ROOT/'compile-fixture.mjs'),str(source),str(output.resolve())], check=True)
        cases.append(dict(name=source.stem, source='programs/' + source.name,
                          source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                          bytecode='bytecode/' + output.name,
                          bytecode_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                          expected_exit=coverage.get('exit_codes', {}).get(source.name,
                                         3 if source.name in coverage['expected_failures'] else 0),
                          timeout_seconds=coverage.get('timeouts', {}).get(source.name, 30),
                          features=coverage['programs'][source.name]))
        if cases[-1]['expected_exit'] == 0:
            cases[-1]['expected_return'] = coverage.get('return_values', {}).get(source.name)
        if source.name in coverage.get('compiler_features', {}):
            cases[-1]['compiler_features'] = coverage['compiler_features'][source.name]
    original = (args.output / (cases[0]['name'] + '.dslb')).read_bytes()
    for name, offset in [('090-bad-bytecode', 0), ('091-schema-mismatch', 6)]:
        data = bytearray(original)
        data[offset] ^= 0xFF
        output = args.output / (name + '.dslb')
        output.write_bytes(data)
        cases.append(dict(name=name, bytecode='bytecode/' + output.name,
                          bytecode_sha256=hashlib.sha256(data).hexdigest(),
                          expected_exit=3,
                          mutation=dict(source=cases[0]['name'], byte_offset=offset),
                          features=['loader ' + name[4:]]))
    # DSLB v6 is the only accepted version: a v5 file must be refused at load.
    data = bytearray(original)
    assert data[:4] == b'DSLB' and data[4:6] == b'\x00\x06'
    data[5] = 5
    output = args.output / '093-v5-refused.dslb'
    output.write_bytes(data)
    cases.append(dict(name='093-v5-refused', bytecode='bytecode/093-v5-refused.dslb',
                      bytecode_sha256=hashlib.sha256(data).hexdigest(),
                      expected_exit=3,
                      mutation=dict(source=cases[0]['name'], bytecode_version=5),
                      features=['loader v5 refused']))
    source_name = '055-object-handles'
    raw = (args.output / (source_name + '.dslb')).read_bytes()
    before = b'fn host_echo_money(Money) -> Money'
    after = b'fn host_echo_money(Items) -> Money'
    assert before in raw and len(before) == len(after)
    changed = raw.replace(before, after)
    name = '092-wrong-handle-import'
    (args.output / (name + '.dslb')).write_bytes(changed)
    cases.append(dict(name=name, bytecode='bytecode/' + name + '.dslb',
                      bytecode_sha256=hashlib.sha256(changed).hexdigest(), expected_exit=3,
                      mutation=dict(source=source_name, import_from=before.decode(), import_to=after.decode()),
                      features=['declared wrong handle type load error']))
    # Alternate output is for reproducibility checks and never changes the manifest.
    if args.output.resolve() == (ROOT / 'bytecode').resolve():
        manifest = dict(format=1, schema='sample.dsl.json', bytecode_version=6,
                        schema_sha256=hashlib.sha256((ROOT / 'sample.dsl.json').read_bytes()).hexdigest(),
                        compiler_minimum='mono-main-0255ef01', cases=cases)
        manifest['fixtures'] = {'invalid.bin': 'ff00c328800a', 'zero-bytes.bin': '610062', 'chunk.bin': '7800c3a9'}
        (ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', newline='\n')
    print(f'Compiled {len(cases)} sample cases')

if __name__ == '__main__':
    main()
