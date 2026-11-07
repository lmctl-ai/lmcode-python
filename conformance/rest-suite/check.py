#!/usr/bin/env python3
"""Integrity check of the shared REST suite (runs in the spec repo's CI, no runtime needed).

* host.schema.json is byte-identical to std/rest/lmcode-rest.schema.json and declares exactly 18 signatures + RestHandler;
* app.dslb is DSLB v6, bound to sha256(host.schema.json), imports only declared/std names, and its RestHandler entries
  are exactly the annotations app.lms routes to;
* scenarios.json is well formed and ends with the rest_stop() scenario.
With --rebuild the bytecode is regenerated with the published compiler (LMSCRIPT_BIN) and must be byte-identical.
"""
import hashlib, json, os, re, struct, subprocess, sys, tempfile
here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(os.path.dirname(here))
read = lambda *p: open(os.path.join(*p), 'rb').read()
fail = lambda m: sys.exit('rest-suite: ' + m)

schema_bytes = read(here, 'host.schema.json')
if schema_bytes != read(root, 'std', 'rest', 'lmcode-rest.schema.json'): fail('host.schema.json differs from std/rest/lmcode-rest.schema.json')
schema = json.loads(schema_bytes)
sigs = [f'fn {n}({", ".join(d["params"])}) -> {d["returns"]}' for n, ds in schema['functions'].items() for d in ds]
sigs += [f'method {t}.{n}({", ".join(d["params"])}) -> {d["returns"]}' for t, td in schema['types'].items() for n, ds in td['methods'].items() for d in ds]
if len(sigs) != 18: fail(f'expected 18 signatures, found {len(sigs)}')
if schema['interfaces'] != {'RestHandler': {'params': [{'name': 'exchange', 'type': 'RestExchange'}], 'returns': 'void'}}: fail('interface RestHandler changed')

code = read(here, 'app.dslb')
if code[:4] != b'DSLB' or struct.unpack('>H', code[4:6])[0] != 6: fail('app.dslb is not DSLB v6')
if code[6:38] != hashlib.sha256(schema_bytes).digest(): fail('app.dslb is bound to a different host.schema.json')
pos = 38
(nconst,) = struct.unpack('>I', code[pos:pos + 4]); pos += 4
consts = []
for _ in range(nconst):
    tag = code[pos]; (n,) = struct.unpack('>I', code[pos + 1:pos + 5]); consts.append(code[pos + 5:pos + 5 + n].decode('latin1')); pos += 5 + n
    if tag != 1: fail('unexpected constant tag')
(nimp,) = struct.unpack('>H', code[pos:pos + 2]); pos += 2
imports = [consts[struct.unpack('>I', code[pos + 4 * i:pos + 4 * i + 4])[0]] for i in range(nimp)]
std = {'fn str_is_int(string) -> bool', 'fn str_to_int(string) -> int', 'fn json_parse(string) -> Json', 'method Json.get(string) -> Json', 'method Json.len() -> int', 'method Json.at(int) -> Json', 'method Json.as_int() -> int'}
for imp in imports:
    if imp not in sigs and imp not in std and not imp.startswith('fn str('): fail(f'unexpected import {imp}')
for needed in ('fn rest_route(string, string, string) -> void', 'fn rest_serve() -> void', 'fn rest_stop() -> void'):
    if needed not in imports: fail(f'program does not import {needed}')
# Every `implements RestHandler` function in app.lms is routed exactly once by annotation name.
source = read(here, 'app.lms').decode()
annotated = re.findall(r'@(\w+)\s*\nfn \w+\(x: RestExchange\) -> void implements RestHandler', source)
routed = re.findall(r'rest_route\("[A-Z]+", "[^"]+", "(\w+)"\)', source)
if sorted(set(annotated)) != sorted(set(routed)) or len(annotated) != len(set(annotated)): fail(f'annotations {annotated} vs routed {routed}')
if f'interface RestHandler(RestExchange) -> void' not in consts: fail('entry interface text missing from the bytecode constants')

doc = json.loads(read(here, 'scenarios.json'))
if doc['version'] != 2 or doc['options'] != {'max_body_bytes': 1024}: fail('scenario options changed')
names = [s['name'] for g in ('stream', 'fatal', 'silent') for s in doc[g]]
if len(names) != 40 or len(set(names)) != 40: fail(f'expected 40 uniquely named scenarios, found {len(names)}')
stream = doc['stream']
if not stream[-2].get('stops_server') or not stream[-1].get('unanswered'): fail('the stream must end with the rest_stop() scenario and an unanswered request')
for s in stream + doc['fatal']:
    if not isinstance(s['expect']['status'], int): fail(f'{s["name"]}: status')
    if 'raw' not in s and not (s['target'].startswith('/') and s['method'].isupper()): fail(f'{s["name"]}: bad request line')

if '--rebuild' in sys.argv:
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, 'suite'); os.makedirs(copy)
        for f in ('app.lms', 'host.schema.json', 'build.mjs'): open(os.path.join(copy, f), 'wb').write(read(here, f))
        subprocess.run(['node', os.path.join(copy, 'build.mjs'), os.environ.get('LMSCRIPT_BIN', 'lmscript')], check=True)
        if read(copy, 'app.dslb') != code: fail('app.dslb differs from a fresh compile of app.lms (run node build.mjs)')
print(f'rest-suite ok: {len(sigs)} signatures, {len(imports)} imports, {len(names)} scenarios (stream/fatal/silent)')
