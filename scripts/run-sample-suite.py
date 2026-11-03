#!/usr/bin/env python3
"""Check the Shop/Ledger host protocol and all pinned byte/exit cases."""
from __future__ import annotations
import hashlib, json, os, pathlib, shutil, subprocess, sys, tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
CORPUS=ROOT/"sample-suite"/"corpus"
SCHEMA_FILE="sample.dsl.json"

def digest(data):return hashlib.sha256(data).hexdigest()
def run_host(args,env=None):
    values=os.environ.copy();values["PYTHONPATH"]=str(ROOT)
    if env:values.update(env)
    return subprocess.run([sys.executable,"-m","sample.main",*args],cwd=ROOT,env=values,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
def frame_value(result):
    lines=result.stdout.decode("utf-8").rstrip("\n").split("\n")
    if len(lines)<3 or lines[0]!="LMCODE_RETURN_BEGIN" or lines[-1]!="LMCODE_RETURN_END":raise AssertionError("CLI usage did not produce one terminal lmcode frame")
    return json.loads(lines[-2])
def schema_signatures(schema):
    values=[]
    for name,overloads in schema.get("functions",{}).items():
        for item in overloads:values.append("fn "+name+"("+", ".join(item.get("params",[]))+") -> "+item.get("returns","void"))
    for owner,definition in schema.get("types",{}).items():
        for name,overloads in definition.get("methods",{}).items():
            for item in overloads:values.append("method "+owner+"."+name+"("+", ".join(item.get("params",[]))+") -> "+item.get("returns","void"))
    return "\n".join(sorted(values))+"\n"
def verify_pins(manifest,schema_bytes):
    if digest(schema_bytes)!=manifest["schema_sha256"]:raise AssertionError("sample schema digest differs from manifest")
    for item in manifest["cases"]:
        if digest((CORPUS/item["bytecode"]).read_bytes())!=item["bytecode_sha256"]:raise AssertionError(item["name"]+": bytecode digest mismatch")
        if item.get("source") and digest((CORPUS/item["source"]).read_bytes())!=item["source_sha256"]:raise AssertionError(item["name"]+": source digest mismatch")
def verify_protocol(schema,schema_bytes):
    result=run_host(["--version"])
    if result.returncode or result.stdout!=b"lmcode-python-sample 0.1.0\n" or result.stderr:raise AssertionError("version protocol mismatch")
    for args in (("--lmcode-schema",),("--lmcode-schema","--json")):
        result=run_host(args)
        if result.returncode or result.stdout!=schema_bytes or result.stderr:raise AssertionError("schema protocol mismatch")
    result=run_host(["--lmcode-signatures"])
    if result.returncode or result.stdout.decode("utf8")!=schema_signatures(schema) or result.stderr:raise AssertionError("signature protocol mismatch")
    retired="--"+"".join(("d","s","l"))
    for args in ((retired,str(CORPUS/"missing-bytecode")),(retired+"-schema",),(retired+"-signatures",),(),("--unknown",),("--lmcode",)):
        result=run_host(list(args));frame=frame_value(result)
        if result.returncode!=2 or frame.get("code")!="CLI_USAGE" or frame.get("phase")!="cli" or result.stderr:raise AssertionError("CLI usage control changed")
    print("PASS sample host CLI protocol")
def check_compiler_errors():
    compiler=os.environ.get("LMCODE_COMPILER") or os.environ.get("LMSCRIPT_BIN") or "lmscript"
    compiler=shutil.which(compiler) or compiler
    if not pathlib.Path(compiler).exists() and not shutil.which(compiler):raise RuntimeError("compiler not found; install @lmctl-ai/lmctl locally and set LMCODE_COMPILER")
    cases=json.loads((CORPUS/"compile-errors"/"manifest.json").read_text(encoding="utf8"))["cases"]
    for item in cases:
        args=["--check",str(CORPUS/"compile-errors"/item["source"])]
        if pathlib.Path(compiler).name.lower().startswith("lmctl"):
            args=["script",*args]
        result=subprocess.run([compiler,*args],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=(os.name=="nt" and compiler.lower().endswith((".cmd",".bat"))))
        stderr=result.stderr.decode("utf8",errors="replace")
        location=f":{item['line']}:{item['column']}:" if item.get("line") else ""
        if result.returncode!=item["exit"] or item["diagnostic"] not in stderr or location and location not in stderr:
            raise AssertionError(f"compiler rejection {item['source']} differs: exit={result.returncode}, stderr={stderr}")
    print(f"PASS {len(cases)} compiler rejection cases")
def run_case(item,manifest):
    with tempfile.TemporaryDirectory(prefix="lmcode-python-sample-") as temp:
        fixture_values={**manifest.get("fixtures",{}),**item.get("fixtures",{})}
        for name,hex_data in fixture_values.items():
            if pathlib.Path(name).name!=name:raise AssertionError("unsafe fixture path")
            pathlib.Path(temp,name).write_bytes(bytes.fromhex(hex_data))
        result=run_host(["--lmcode",str(CORPUS/item["bytecode"])],{"SAMPLE_TMP":temp})
        expected=(CORPUS/"expected"/(item["name"]+".out")).read_bytes()
        exit_code=int((CORPUS/"expected"/(item["name"]+".exit")).read_text(encoding="ascii"))
        if result.returncode!=exit_code or result.stdout!=expected or result.stderr:
            raise AssertionError(f"{item['name']}: exit {result.returncode}/{exit_code}; stdout {len(result.stdout)}/{len(expected)} bytes; stderr={result.stderr.decode('utf8',errors='replace')}")
def main():
    manifest=json.loads((CORPUS/"manifest.json").read_text(encoding="utf8"));schema_bytes=(CORPUS/manifest["schema"]).read_bytes();schema=json.loads(schema_bytes)
    verify_pins(manifest,schema_bytes);verify_protocol(schema,schema_bytes);check_compiler_errors();passed=0;failures=[]
    for item in manifest["cases"]:
        try:run_case(item,manifest);passed+=1
        except Exception as error:failures.append((item["name"],error))
    for name,error in failures:print("FAIL "+name+": "+str(error),file=sys.stderr)
    print(("PASS " if not failures else "FAIL ")+str(passed)+"/"+str(len(manifest["cases"]))+" sample byte/exit cases")
    return int(bool(failures))
if __name__=="__main__":raise SystemExit(main())
