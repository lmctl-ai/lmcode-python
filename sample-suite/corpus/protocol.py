#!/usr/bin/env python3
"""Check the host discovery/usage protocol separately from program stdout."""
import json
from pathlib import Path
import re
import subprocess
import sys
ROOT = Path(__file__).resolve().parent


def declared_signatures(schema):
    out = ['context ' + name + ': ' + value for name, value in schema['context'].items()]
    for name, declarations in schema['functions'].items():
        for value in declarations:
            out.append('fn ' + name + '(' + ', '.join(value['params']) + ') -> ' + value['returns'])
    for owner, definition in schema['types'].items():
        for name, declarations in definition['methods'].items():
            for value in declarations:
                result = owner if value['returns'] == 'self' else value['returns']
                out.append('method ' + owner + '.' + name + '(' + ', '.join(value['params']) + ') -> ' + result)
    return ('\n'.join(sorted(out)) + '\n').encode()


def check(command):
    def call(*args):
        result = subprocess.run([*command, *args], capture_output=True, timeout=30)
        if result.stderr:
            raise ValueError('protocol wrote stderr: ' + result.stderr.decode(errors='replace'))
        return result
    version = call('--version')
    if version.returncode or not re.fullmatch(rb'lmcode-[a-z]+-sample [0-9]+\.[0-9]+\.[0-9]+\n', version.stdout):
        raise ValueError('invalid --version protocol')
    for args in [('--lmcode-schema',), ('--lmcode-schema', '--json')]:
        result = call(*args)
        if result.returncode or result.stdout != (ROOT / 'sample.dsl.json').read_bytes():
            raise ValueError('schema discovery bytes differ')
    result = call('--lmcode-signatures')
    if result.returncode or result.stdout != declared_signatures(json.loads((ROOT / 'sample.dsl.json').read_text())):
        raise ValueError('schema/registry signature mismatch')
    retired = '--' + 'dsl'
    for suffix in ['', '-schema', '-signatures']:
        result = call(*([retired, str(ROOT / 'does-not-exist.dslb')] if not suffix else [retired + suffix]))
        value = json.loads(result.stdout.splitlines()[-2])
        if result.returncode != 2 or value.get('code') != 'CLI_USAGE':
            raise ValueError('retired option must be rejected before opening input')
    for args in [(), ('--unknown',), ('--lmcode',), ('--lmcode-schema', '--bad')]:
        result = call(*args)
        value = json.loads(result.stdout.splitlines()[-2])
        if result.returncode != 2 or value.get('code') != 'CLI_USAGE' or value.get('phase') != 'cli' or value.get('ok') is not False:
            raise ValueError('usage must produce one JSON CLI_USAGE and exit 2')
    result = call('--lmcode', str(ROOT / 'does-not-exist.dslb'))
    value = json.loads(result.stdout.splitlines()[-2])
    if result.returncode != 4 or value.get('code') != 'APP_FAIL':
        raise ValueError('unreadable input must produce APP_FAIL and exit 4')
    print('PASS host CLI protocol (0/2/3/4; schema/signatures/discovery)')

if __name__ == '__main__':
    try:
        check(sys.argv[1:])
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        sys.exit('protocol error: ' + str(error))
