#!/usr/bin/env python3
"""Cross-platform verification for the SDK's vendored source snapshots."""
from __future__ import annotations
import hashlib, json, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]

def digest(directory, dot_prefix=False):
    rows=[]
    for path in sorted((p for p in directory.rglob("*") if p.is_file()),key=lambda p:p.relative_to(directory).as_posix()):
        relative=path.relative_to(directory).as_posix()
        if dot_prefix:relative="./"+relative
        rows.append(hashlib.sha256(path.read_bytes()).hexdigest()+"  "+relative+"\n")
    return hashlib.sha256("".join(rows).encode()).hexdigest()

def locked_tree(name,dot_prefix=False):
    directory=ROOT/"conformance"/name
    lock=ROOT/(name+".lock")
    expected=next((line.split("=",1)[1] for line in lock.read_text().splitlines() if line.startswith("sha256=")),"")
    actual=digest(directory,dot_prefix)
    if not expected or expected!=actual:raise SystemExit(name+" pin mismatch: "+actual)
    print(name+" pin verified")

def main():
    for suite in ("vectors","stdlib-vectors","return-vectors","invocation-vectors"):locked_tree(suite,True)
    locked_tree("rest-suite")
    schema=ROOT/"std/lmcode-std.schema.json"
    data=json.loads(schema.read_text(encoding="utf8"))
    count=sum(map(len,data.get("functions",{}).values()))+sum(sum(map(len,t.get("methods",{}).values())) for t in data.get("types",{}).values())
    if count!=206:raise SystemExit("standard signature count differs: "+str(count))
    for name in ("std","std-docs"):
        path=ROOT/("std/lmcode-std.schema.json" if name=="std" else "std/lmcode-std.docs.json")
        lock=ROOT/(name+".lock");expected=next((x.split("=",1)[1] for x in lock.read_text().splitlines() if x.startswith("sha256=")),"")
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise SystemExit(name+" pin mismatch")
    sample=ROOT/"sample-suite/corpus";lock=ROOT/"sample-suite.lock"
    expected=next((x.split("=",1)[1] for x in lock.read_text().splitlines() if x.startswith("sha256=")),"")
    if digest(sample,False)!=expected:raise SystemExit("sample-suite pin mismatch")
    if (ROOT/"sample/data/sample.dsl.json").read_bytes()!=(sample/"sample.dsl.json").read_bytes():raise SystemExit("packaged sample schema drift")
    print("standard schema/docs and sample suite pins verified")
if __name__=="__main__":main()
