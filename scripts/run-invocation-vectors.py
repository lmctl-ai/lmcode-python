#!/usr/bin/env python3
"""Run canonical manifest, dry-mode, and result-frame vectors."""
from __future__ import annotations
import json, pathlib, sys
import os, subprocess, tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from lmcode import Context, HostError, InvocationResults, LmcodeError, Registry, dry, load
from lmcode.results import ResultContract

DIR=ROOT/"conformance"/"invocation-vectors"

def make_registry():
    registry=Registry()
    counter=[0]
    def next_counter(ctx,self_obj,args):counter[0]+=1;return counter[0]
    registry.function("next_counter",[],"int",next_counter)
    registry.function("entry_fail",[],"void",lambda ctx,self_obj,args:(_ for _ in ()).throw(HostError("native entry failure")),dry(lambda ctx,self_obj,args:(_ for _ in ()).throw(HostError("preview failed"))))
    registry.function("wp90_Json",[],"Json",lambda ctx,self_obj,args:(_ for _ in ()).throw(HostError("real dummy callback ran")))
    registry.function("wp90_consume",["Json"],"int",lambda ctx,self_obj,args:(_ for _ in ()).throw(HostError("real consumer ran")))
    bad=lambda ctx,self_obj,args:(_ for _ in ()).throw(HostError("preview received dry null"))
    registry.method("Json","wp90_consume",["Json"],"int",bad)
    registry.method("Json","wp90_preview",["Json"],"int",bad,dry(bad))
    return registry

def main():
    manifest=json.loads((DIR/"manifest.json").read_text(encoding="utf8"));failures=[];registry_tests=0
    for row in manifest["cases"]:
        name=row["name"]
        try:
            config=json.loads((DIR/(name+".json")).read_text(encoding="utf8"))
            files=[str((DIR/(program+".slot-"+str(i)+".lmcode")).resolve()) for i,program in enumerate(row["programs"])]
            registry=make_registry()
            if row["mode"] is None:
                results=InvocationResults.from_command(files,env={})
            else:
                metadata={"version":1,"mode":row["mode"],"dry":row.get("dry",config.get("dry",False)),"parts":[{"index":i,"file":file} for i,file in enumerate(files)]}
                results=InvocationResults.from_metadata(json.dumps(metadata,separators=(",",":" )).encode(),files)
            schema=(DIR/row.get("schema",manifest["schema"])).read_bytes();contract=ResultContract.from_schema(schema)
            context=Context();context.dry_mode=results.dry_mode()
            for index in config["execution"]:
                phase="load"
                try:
                    program=load((DIR/(row["programs"][index]+".dslb")).read_bytes(),schema,registry)
                    results.select(index,registry,contract);phase="run"
                    context.result_sink=registry.result_sink
                    program.run(context,registry)
                    for entry_index in range(len(program.entries)):
                        result=program.call(entry_index,context,registry,[])
                        if type(result) is not int or result!=7:raise HostError("entry HALT result changed")
                    results.complete(index)
                except Exception as error:
                    results.fail(index,phase,error);break
            if config.get("app_fail"):
                results.fail(None,"app",LmcodeError("APP_FAIL","native validation failed"))
            actual=results.write_frame();expected=(DIR/(name+".expect")).read_text(encoding="utf8")
            if actual["code"]!=row["exit"] or actual["frame"]!=expected:
                raise AssertionError("exit/frame mismatch: "+repr(actual)+" expected "+repr(expected))
            registry_tests+=1
        except Exception as error:failures.append((name,error))
    # Metadata controls cover strict v1 shape, dry-field typing, path slots and registration uniqueness.
    controls=[
      (b'{"version":1,"mode":"single","parts":[]}',"dry must be boolean"),
      (b'{"version":1,"mode":"single","dry":1,"parts":[]}',"dry must be boolean"),
      (b'{"version":1,"mode":"single","dry":true,"parts":[{"index":0,"file":"relative"}]}',"file must be absolute"),
    ]
    for raw,message in controls:
      try: InvocationResults.from_metadata(raw,["/tmp/vector"])
      except LmcodeError as error:
        if message not in error.message:failures.append(("manifest-control",AssertionError(error.message)))
      else:failures.append(("manifest-control",AssertionError("invalid manifest accepted")))
    metadata_cases=json.loads((DIR/"metadata-errors.json").read_text(encoding="utf8"))
    with tempfile.TemporaryDirectory(prefix="lmcode-python-metadata-") as temporary:
      metadata_path=pathlib.Path(temporary)/"invocation.json"
      for case in metadata_cases:
        metadata_path.write_bytes(bytes.fromhex(case["raw_hex"]))
        env=dict(os.environ,LMCODE_INVOCATION_FILE=str(metadata_path))
        result=subprocess.run([sys.executable,"-m","sample.main","--lmcode","/unused"],cwd=ROOT,env=env,capture_output=True)
        expected=case["frame"].encode("utf8")
        if (result.returncode,result.stdout,result.stderr)!=(2,expected,b""):
          failures.append(("metadata:"+case["name"],AssertionError(repr((result.returncode,result.stdout,result.stderr)))))
        else:
          print("PASS metadata bytes "+case["name"])
    for name,error in failures:print("FAIL "+name+": "+str(error),file=sys.stderr)
    print(("PASS " if not failures else "FAIL ")+str(registry_tests)+"/"+str(len(manifest["cases"]))+" invocation goldens; "+str(len(controls))+" metadata controls; "+str(len(metadata_cases)-sum(1 for name,error in failures if name.startswith("metadata:")))+"/"+str(len(metadata_cases))+" canonical metadata errors")
    return 1 if failures or registry_tests!=len(manifest["cases"]) else 0

if __name__=="__main__":raise SystemExit(main())
