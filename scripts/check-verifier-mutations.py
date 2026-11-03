#!/usr/bin/env python3
"""Prove verifier regression tests fail when individual structural checks are removed."""
from __future__ import annotations
import os, pathlib, shutil, subprocess, sys, tempfile

ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'lmcode'/'loader.py'
TEST=ROOT/'tests'/'test_verifier_controls.py'
ORIGINAL=SOURCE.read_text(encoding='utf-8')
MUTATIONS={
    'hidden-store': ('if op == "STORE_LOCAL" and region.locals[idx].hidden:\n                _fail("STORE_LOCAL at offset " + str(pc) + " writes compiler-owned loop local " + str(idx))', ''),
    'duplicate-entry': ('''        if any(entry.name == name for entry in entries): _fail("duplicate entry name '" + name + "'")''', '''        if False: pass'''),
    'backward-jump': ('if rel < 0: _fail("jump at offset " + str(ins.pc) + " goes backwards outside a range loop")', 'if False: pass'),
    'stack-underflow': ('if depth < pop: _fail("operand stack underflow at offset " + str(pc))', 'if False: pass'),
}

def run(package: pathlib.Path) -> subprocess.CompletedProcess:
    env=dict(os.environ)
    env['PYTHONPATH']=str(package)
    env['LMCODE_TEST_ROOT']=str(ROOT)
    return subprocess.run([sys.executable,'-m','unittest','discover','-s',str(package/'tests'),'-p','test_verifier_controls.py'],cwd=package,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)

def main() -> int:
    base=run(ROOT)
    if base.returncode:
        print(base.stdout); print('baseline verifier tests must pass'); return 1
    print('baseline verifier tests pass')
    for name,(before,after) in MUTATIONS.items():
        if before not in ORIGINAL:
            print('mutation anchor missing: '+name); return 1
        with tempfile.TemporaryDirectory(prefix='lmcode-verifier-mutation-') as directory:
            temp=pathlib.Path(directory)
            shutil.copytree(ROOT/'lmcode',temp/'lmcode',ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree(ROOT/'tests',temp/'tests',ignore=shutil.ignore_patterns('__pycache__'))
            target=temp/'lmcode'/'loader.py'
            target.write_text(ORIGINAL.replace(before,after,1),encoding='utf-8')
            result=run(temp)
            if result.returncode == 0:
                print('mutant survived: '+name); return 1
            print(name+': rejected by its regression test')
    print('PASS verifier mutation controls')
    return 0

if __name__=='__main__': raise SystemExit(main())
