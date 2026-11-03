#!/usr/bin/env python3
"""Run canonical result-sink and terminal-frame vectors."""
from __future__ import annotations
import json, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from lmcode import HostError, InvocationResults, LmcodeError, Registry, ResultContract, load
DIR=ROOT/"conformance"/"return-vectors"

def main():
    manifest=json.loads((DIR/"manifest.json").read_text(encoding="utf8"));failures=[];passed=0;schema=(DIR/manifest["schema"]).read_bytes()
    for vector in manifest["vectors"]:
        name=vector["name"];path=str((DIR/vector["bytecode"]).resolve());results=InvocationResults.from_command([path],env={});registry=Registry();contract=ResultContract.from_schema(schema);sink=results.select(0,registry,contract)
        registry.function("entry_fail",[],"void",lambda ctx,self_obj,args:(_ for _ in ()).throw(HostError("entry failure")))
        registry.function("expect_result",["string"],"void",lambda ctx,self_obj,args:None if sink.json()==args[0] else (_ for _ in ()).throw(HostError("return overload payload mismatch")))
        error=None;phase="run"
        try:
            program=load((DIR/vector["bytecode"]).read_bytes(),schema,registry);sink.reset();ctx=__import__('lmcode').Context();program.run(ctx,registry)
            for _ in range(vector.get("repeat",1)):
                for i in range(len(program.entries)):
                    result=program.call(i,ctx,registry,[])
                    if type(result) is not int or result!=7:raise HostError("entry HALT result changed")
            results.complete(0)
        except Exception as exc:
            error=exc;results.fail(0,phase,exc)
        output=results.write_frame();expected=(DIR/vector["expect"]["file"]).read_text(encoding="utf8")
        if output["code"]!=vector["expect"]["exit"] or output["frame"]!=expected:failures.append((name,"frame/exit mismatch "+repr(output)+" expected "+repr(expected)))
        else:passed+=1
    for name,message in failures:print("FAIL "+name+": "+message,file=sys.stderr)
    print(("PASS " if not failures else "FAIL ")+str(passed)+"/"+str(len(manifest["vectors"]))+" return vectors")
    return int(bool(failures))
if __name__=="__main__":raise SystemExit(main())
