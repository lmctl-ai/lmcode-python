#!/usr/bin/env python3
"""Fail when a std signature is added but not called by the shared bytecode corpus."""
import argparse
import json
import runpy
from pathlib import Path
import struct
ROOT = Path(__file__).resolve().parent


def signatures(schema):
    result = set()
    def add(prefix, name, declarations):
        for decl in declarations:
            result.add(prefix + name + '(' + ', '.join(decl['params']) + ') -> ' + decl['returns'])
    for name, declarations in schema.get('functions', {}).items(): add('fn ', name, declarations)
    for owner, definition in schema.get('types', {}).items():
        for name, declarations in definition['methods'].items(): add('method ' + owner + '.', name, declarations)
    return result


def imports(path):
    data = path.read_bytes()
    offset = 38
    def number(fmt):
        nonlocal offset
        value = struct.unpack_from('>' + fmt, data, offset)[0]
        offset += struct.calcsize(fmt)
        return value
    constants = []
    for _ in range(number('I')):
        assert number('B') == 1
        size = number('I')
        constants.append(data[offset:offset+size].decode('utf-8'))
        offset += size
    return {constants[number('I')] for _ in range(number('H'))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--std', type=Path, default=ROOT.parent / 'std/lmcode-std.schema.json')
    args = parser.parse_args()
    required = signatures(json.loads(args.std.read_text()))
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    actual = set().union(*(imports(ROOT / case['bytecode']) for case in manifest['cases'] if not case.get('mutation')))
    missing = required - actual
    if missing:
        raise SystemExit('UNEXERCISED STANDARD SIGNATURES:\n' + '\n'.join(sorted(missing)))
    schema = json.loads((ROOT / 'sample.dsl.json').read_text())
    declared = runpy.run_path(str(ROOT / 'protocol.py'))['declared_signatures'](schema).decode().splitlines()
    host = {signature for signature in declared if not signature.startswith('context ')} - required
    if host - actual:
        raise SystemExit('UNEXERCISED HOST SIGNATURES:\n' + '\n'.join(sorted(host - actual)))
    print(f'PASS: all {len(required)} standard signatures are imported by the corpus')
    print(f'PASS: all {len(host)} host signatures are imported by the corpus')

if __name__ == '__main__':
    main()
