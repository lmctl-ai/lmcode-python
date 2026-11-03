"""Invocation manifest v1, per-part result sinks, and terminal frame collection."""
from __future__ import annotations
import json, os, ntpath
from dataclasses import dataclass
from .errors import HostError, LmcodeError, sdk_errors
from .registry import Registry
from .results import ResultContract, ResultSink, failure_frame, _serialize_json, success_frame
from .stdlib import JsonNode, _parse_json

_UNSET=object()

def _cli(message): return LmcodeError("CLI_USAGE","lmcode invocation: "+message)
def _native(node):
    if isinstance(node,JsonNode):
        if node.kind in ("null","bool","int","float","string"):return node.value
        if node.kind=="array":return [_native(v) for v in node.array]
        if node.kind=="object":return {m.key:_native(m.value) for m in node.members}
    return node
def _manifest_error(error):
    message=error.message
    if message=="json_parse: BOM is not allowed at byte 0":message="JSON BOM is not allowed"
    if message.startswith("json_parse: trailing input at byte "):message="trailing JSON input"
    return _cli(message)

def _pointer(parent,key):
    return parent+"/"+str(key).replace("~","~0").replace("/","~1")

def _validate_manifest_numbers(node,path=""):
    if not isinstance(node,JsonNode):return
    if node.kind=="int" and abs(node.value)>(1<<53)-1:
        raise _cli("lmcode return: invalid JSON value at "+(path or "")+": unsafe_integer")
    if node.kind=="float":
        significand=node.raw.split("e")[0].split("E")[0]
        if node.value==0.0 and any(char in "123456789" for char in significand):
            raise _cli("lmcode return: invalid JSON value at "+(path or "")+": underflow")
        if node.value.is_integer() and abs(node.value)>(1<<53)-1:
            raise _cli("lmcode return: invalid JSON value at "+(path or "")+": unsafe_integer")
    if node.kind=="array":
        for index,item in enumerate(node.array):_validate_manifest_numbers(item,_pointer(path,index))
    elif node.kind=="object":
        for member in node.members:_validate_manifest_numbers(member.value,_pointer(path,member.key))
def _is_absolute(path):return os.path.isabs(path) or (os.name=="nt" and ntpath.isabs(path))
def _only_keys(value,allowed):
    if not isinstance(value,dict):raise _cli("object required")
    for key in value:
        if key not in allowed:raise _cli("unknown key "+key)
def _integer(value):
    if type(value) is int and abs(value)<=(1<<53)-1:return value
    if type(value) is float and abs(value)<=(1<<53)-1 and value.is_integer():return int(value)
    return None

def _manifest_metadata(metadata,files):
    _only_keys(metadata,{"version","mode","dry","parts"})
    if _integer(metadata.get("version"))!=1:raise _cli("unsupported version")
    mode=metadata.get("mode")
    if mode not in ("single","builder"):raise _cli("invalid mode")
    dry=metadata.get("dry",_UNSET)
    if type(dry) is not bool:raise _cli("dry must be boolean")
    parts=metadata.get("parts")
    if not isinstance(parts,list) or not parts or mode=="single" and len(parts)!=1:raise _cli("invalid parts")
    indices={}
    for i,part in enumerate(parts):
        _only_keys(part,{"index","file"})
        if _integer(part.get("index"))!=i:raise _cli("noncontiguous index")
        file=part.get("file")
        if not isinstance(file,str) or "\0" in file or not _is_absolute(file):raise _cli("file must be absolute")
        if file in indices:raise _cli("duplicate file")
        indices[file]=i
    if len(files)!=len(indices):raise _cli("registration count mismatch")
    registrations=[];seen=set()
    for file in files:
        if file not in indices:raise _cli("extra registration")
        index=indices[file]
        if index in seen:raise _cli("duplicate registration")
        seen.add(index);registrations.append(Registration(file,index))
    return mode=="builder",dry,registrations

@dataclass(frozen=True)
class Registration:
    file: str
    index: int

class InvocationResults:
    def __init__(self,builder,dry,registrations):
        self.builder=builder;self.dry=dry;self.registrations=registrations
        self.slots=[{"sink":None,"result":_UNSET} for _ in registrations]
        self.failure=None;self.writing=False
    @classmethod
    @sdk_errors("CLI_USAGE")
    def from_metadata(cls,raw,files):
        try:parsed=_parse_json(bytes(raw).decode("latin-1"))
        except LmcodeError as error:raise _manifest_error(error)
        dry=parsed.kind=="object" and any(member.key=="dry" and member.value.kind=="bool" and member.value.value for member in parsed.members)
        try:
            _validate_manifest_numbers(parsed)
            metadata=_native(parsed)
            builder,dry,registrations=_manifest_metadata(metadata,list(files))
        except LmcodeError as error:
            if dry:error.invocation_dry=True
            raise
        return cls(builder,dry,registrations)
    @classmethod
    @sdk_errors("CLI_USAGE")
    def from_command(cls,files,env=None):
        env=os.environ if env is None else env
        if "LMCODE_INVOCATION_FILE" in env:
            manifest=env["LMCODE_INVOCATION_FILE"]
            if not isinstance(manifest,str) or not manifest or "\0" in manifest or not _is_absolute(manifest):raise _cli("manifest path must be absolute")
            try:
                with open(manifest,"rb") as stream:raw=stream.read()
            except OSError:raise _cli("cannot read manifest")
            return cls.from_metadata(raw,files)
        if not files:raise _cli("empty parts")
        registrations=[]
        for index,file in enumerate(files):
            if not isinstance(file,str) or not file or "\0" in file:raise _cli("invalid command file")
            try:file.encode("utf-8","strict")
            except UnicodeError:raise _cli("file must be UTF-8")
            registrations.append(Registration(file,index))
        return cls(len(files)>1,False,registrations)
    def dry_mode(self):return self.dry
    def registrations_copy(self):return [Registration(x.file,x.index) for x in self.registrations]
    def _slot(self,index):
        if type(index) is not int or index<0 or index>=len(self.slots):raise HostError("lmcode invocation: invalid slot index")
        return self.slots[index]
    @sdk_errors()
    def select(self,index,registry,contract=None):
        if self.writing:raise HostError("lmcode invocation: finalized")
        slot=self._slot(index)
        if self.failure:raise HostError("lmcode invocation: cannot start work after failure")
        contract=contract or ResultContract()
        if slot["sink"] is None:slot["sink"]=ResultSink(contract)
        elif slot["sink"].contract.type!=contract.type or slot["sink"].contract.nullable!=contract.nullable:raise HostError("lmcode invocation: result contract changed")
        registry.set_result_sink(slot["sink"])
        return slot["sink"]
    @sdk_errors()
    def complete(self,index):
        if self.writing:raise HostError("lmcode invocation: finalized")
        slot=self._slot(index)
        if slot["sink"] is None:raise HostError("lmcode invocation: slot was not selected")
        try:slot["result"]=slot["sink"].complete()
        except (MemoryError,RecursionError) as error:
            message="memory allocation failed" if isinstance(error,MemoryError) else "maximum recursion depth exceeded"
            wrapped=HostError(message);self.fail(index,"run",wrapped);raise wrapped from None
        except Exception as error:self.fail(index,"run",error);raise
    @sdk_errors()
    def fail(self,index,phase,error):
        if self.writing:raise HostError("lmcode invocation: finalized")
        if self.failure is not None:return
        if index is not None:self._slot(index)
        if phase not in ("cli","load","run","app"):raise HostError("lmcode invocation: invalid failure phase")
        if not isinstance(error,LmcodeError):
            message="memory allocation failed" if isinstance(error,MemoryError) else "maximum recursion depth exceeded" if isinstance(error,RecursionError) else str(error)
            error=HostError(message)
        part=index if self.builder and index is not None else None
        self.failure={"phase":phase,"error":error,"part":part}
    @sdk_errors()
    def write_frame(self):
        if self.writing:raise HostError("lmcode invocation: finalized")
        if self.failure is None:
            for i,slot in enumerate(self.slots):
                if slot["result"] is _UNSET:
                    self.fail(i,"run",HostError("lmcode invocation: slot not completed"));break
        if self.failure:
            phase=self.failure["phase"];error=self.failure["error"];part=self.failure["part"]
            code={"cli":2,"load":3,"run":3,"app":4}[phase]
            frame=failure_frame(error,phase,part,self.dry)
        else:
            code=0;values=[slot["result"] for slot in self.slots]
            value={"result":values,"parts":len(values)} if self.builder else {"result":values[0]}
            frame=success_frame(value["result"] if not self.builder else values,self.dry)
            if self.builder:
                # Keep the canonical key order: ok, result, parts, dry.
                payload='{"ok":true,"result":['+','.join(_serialize_json(v) for v in values)+'],"parts":'+str(len(values))+(',"dry":true' if self.dry else '')+'}'
                frame="LMCODE_RETURN_BEGIN\n"+payload+"\nLMCODE_RETURN_END\n"
        self.writing=True
        return {"code":code,"frame":frame}

def result_contract_from_schema(schema):return ResultContract.from_schema(schema)

def failure_frame_for_phase(phase,error):
    collector=InvocationResults(False,False,[]);collector.fail(None,phase,error);return collector.write_frame()
