#!/usr/bin/env python3
"""Pin the canonical Shop/Ledger sample suite from lmcode-cpp."""
from __future__ import annotations
import hashlib, os, pathlib, shutil, subprocess, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=pathlib.Path(os.environ.get("LMCODE_CPP_DIR",ROOT.parent/"lmcode-cpp-wp165-ref")).resolve()
DEST=ROOT/"sample-suite"/"corpus"
LOCK=ROOT/"sample-suite.lock"
def digest(directory):
    rows=[]
    for path in sorted((p for p in directory.rglob("*") if p.is_file()),key=lambda p:p.relative_to(directory).as_posix()):
        rows.append(hashlib.sha256(path.read_bytes()).hexdigest()+"  "+path.relative_to(directory).as_posix()+"\n")
    return hashlib.sha256("".join(rows).encode()).hexdigest()
if len(sys.argv)>1 and sys.argv[1]=="--verify":
    text=LOCK.read_text(encoding="utf-8")
    expected=next((line.split("=",1)[1] for line in text.splitlines() if line.startswith("sha256=")),"")
    if not expected or digest(DEST)!=expected:raise SystemExit("sample-suite corpus differs from lock")
    if (ROOT/"sample"/"data"/"sample.dsl.json").read_bytes()!=(DEST/"sample.dsl.json").read_bytes():raise SystemExit("packaged sample schema differs from canonical corpus")
    print("sample-suite corpus and packaged schema verified")
else:
    if DEST.exists():raise SystemExit("sample-suite corpus already exists; sync refuses to discard local fixture changes")
    source=SOURCE/"sample-suite"
    if not source.is_dir():raise SystemExit("canonical sample-suite missing: "+str(source))
    shutil.copytree(source,DEST)
    (ROOT/"sample"/"data").mkdir(parents=True,exist_ok=True)
    shutil.copyfile(DEST/"sample.dsl.json",ROOT/"sample"/"data"/"sample.dsl.json")
    commit=subprocess.check_output(["git","-C",str(SOURCE),"rev-parse","HEAD"],text=True).strip()
    LOCK.write_bytes(("repo=https://github.com/lmctl-ai/lmcode-cpp\ncommit="+commit+"\nsha256="+digest(DEST)+"\n").encode("utf-8"))
    print("synced sample-suite from lmcode-cpp "+commit)
