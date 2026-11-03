"""Sample CLI host for the canonical Shop/Ledger contract."""
from __future__ import annotations
import os, sys
from pathlib import Path
from lmcode import Context, InvocationResults, LmcodeError, ResultContract, load
from lmcode.results import failure_frame
from .host import Host, Money, entry_text

ROOT=Path(__file__).resolve().parents[1]
SCHEMA_PATH=Path(__file__).parent/"data"/"sample.dsl.json"
VERSION="0.1.0"
USAGE="usage: --version | --lmcode-schema [--json] | --lmcode-signatures | [--lmcode|--first|--last] FILE ..."

class AppFailure(LmcodeError):
    def __init__(self,message):super().__init__("APP_FAIL",message)

def _frame(phase,error):
    frame=failure_frame(error,phase)
    sys.stdout.buffer.write(frame.encode("utf-8"));sys.stdout.buffer.flush()
    return {"cli":2,"load":3,"run":3,"app":4}[phase]

def _discover(args,schema_bytes):
    if args==["--version"]:
        sys.stdout.buffer.write(f"lmcode-python-sample {VERSION}\n".encode());return 0
    if args==["--lmcode-schema"] or args==["--lmcode-schema","--json"]:
        sys.stdout.buffer.write(schema_bytes);return 0
    if args==["--lmcode-signatures"]:
        host=Host()
        sys.stdout.write("\n".join(host.registry.signatures())+"\n");return 0
    return None

def _parse_command(args):
    if len(args)%2 or not args:raise LmcodeError("CLI_USAGE",USAGE)
    parts=[]
    for index in range(0,len(args),2):
        flag,file=args[index:index+2]
        if flag not in ("--lmcode","--first","--last"):raise LmcodeError("CLI_USAGE",USAGE)
        if not file:raise LmcodeError("CLI_USAGE",USAGE)
        priority={"--first":0,"--lmcode":1,"--last":2}[flag]
        parts.append({"file":file,"priority":priority,"index":len(parts)})
    return parts

def _normalize_load_error(error):
    if not isinstance(error,LmcodeError):return LmcodeError("LOAD_BAD_BYTECODE","invalid sample bytecode")
    if error.code=="LOAD_SCHEMA_MISMATCH":return LmcodeError(error.code,"sample schema mismatch")
    if error.code=="LOAD_UNBOUND":return LmcodeError(error.code,"sample import mismatch")
    return LmcodeError(error.code,"invalid sample bytecode")

def _print_entry(name,value):
    raw=f"entry {name} = {entry_text(value)}\n".encode("utf-8")
    sys.stdout.buffer.write(raw)

def run(args=None):
    args=list(sys.argv[1:] if args is None else args)
    try:schema_bytes=SCHEMA_PATH.read_bytes()
    except OSError:return _frame("app",AppFailure("sample schema unavailable"))
    inspected=_discover(args,schema_bytes)
    if inspected is not None:return inspected
    try:parts=_parse_command(args)
    except LmcodeError as error:return _frame("cli",error)
    files=[part["file"] for part in parts]
    try:results=InvocationResults.from_command(files)
    except LmcodeError as error:return _frame("cli",error)
    host=Host(dry_mode=results.dry_mode(),output=sys.stdout.buffer)
    contract=ResultContract.from_schema(schema_bytes)
    context=Context();context.set("shop",host.shop);context.set("ledger",host.ledger);context.dry_mode=results.dry_mode()
    parts.sort(key=lambda part:part["priority"])
    entries_called=0;failed=False
    for part in parts:
        phase="load"
        try:
            try:bytecode=Path(part["file"]).read_bytes()
            except OSError:raise AppFailure("cannot read sample input")
            try:program=load(bytecode,schema_bytes,host.registry)
            except Exception as error:raise _normalize_load_error(error)
            results.select(part["index"],host.registry,contract)
            phase="run";context.result_sink=registry_sink=host.registry.result_sink
            program.run(context,host.registry)
            for index,entry in enumerate(program.entries):
                def invoke(argument):
                    nonlocal entries_called
                    value=program.call(index,context,host.registry,[argument]);entries_called+=1
                    if value is not None:_print_entry(entry.name,value)
                if entry.annotation=="item":
                    for money in host.shop.items.values:invoke(host_money_object(money))
                elif entry.annotation=="total":invoke(host_money_object(host._money(sum(x.cents for x in host.shop.items.values))))
            results.complete(part["index"])
        except Exception as error:
            phase_name="app" if isinstance(error,AppFailure) else phase
            results.fail(part["index"],phase_name,error);failed=True;break
    if not failed and host.ledger.balance<0:results.fail(None,"app",AppFailure("ledger: negative balance"))
    if not failed and results.failure is None:
        sys.stdout.buffer.write(host.summary(entries_called).encode("utf-8"))
    output=results.write_frame()
    sys.stdout.buffer.write(output["frame"].encode("utf-8"));sys.stdout.buffer.flush()
    return output["code"]

def host_money_object(value):
    from lmcode.registry import ObjectRef
    if isinstance(value,ObjectRef):return value
    return ObjectRef("Money",value,id(value))

if __name__=="__main__":raise SystemExit(run())
