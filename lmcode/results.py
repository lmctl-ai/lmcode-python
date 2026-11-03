"""Result contracts, owned JSON sinks, exact JSON and terminal frame encoding."""
from __future__ import annotations
import json, math, re
from .errors import HostError, LmcodeError
from .registry import ObjectRef
from .vm import DryNull

SAFE_INTEGER=9007199254740991
class JsonText(str): pass
SUPPORTED={"null","bool","int","float","string","Json","StrList","IntList","FloatList","StrMap","IntMap","FloatMap"}


def format_frame_float(value):
    if math.isnan(value):return "nan"
    if math.isinf(value):return "inf" if value>0 else "-inf"
    if value==0.0:return "0"
    sign="-" if value<0 else ""
    text=repr(abs(value)).lower()
    if "e" in text:
        mant,exp=text.split("e"); exponent=int(exp)
        digits=mant.replace(".","")
        decimal=(mant.find(".") if "." in mant else len(mant))+exponent
    else:
        mant=text; digits=mant.replace(".","")
        decimal=mant.find(".") if "." in mant else len(mant)
    lead=len(digits)-len(digits.lstrip("0"));digits=digits.lstrip("0") or "0";decimal-=lead
    while len(digits)>1 and digits.endswith("0"):digits=digits[:-1]
    exponent=decimal-1
    if -4<=exponent<6:
        if decimal<=0:return sign+"0."+"0"*(-decimal)+digits
        if decimal>=len(digits):return sign+digits+"0"*(decimal-len(digits))
        return sign+digits[:decimal]+"."+digits[decimal:]
    mantissa=digits if len(digits)==1 else digits[0]+"."+digits[1:]
    return sign+mantissa+"e"+("-" if exponent<0 else "+")+str(abs(exponent)).rjust(2,"0")


def quote_json(text):
    return json.dumps(text,ensure_ascii=False,separators=(",",":" )).replace("\u2028","\\u2028").replace("\u2029","\\u2029")


def _pointer(parent,key):return parent+"/"+str(key).replace("~","~0").replace("/","~1")
def _invalid(path,reason):raise HostError("lmcode return: invalid JSON value at "+path+": "+reason)
def _decode_vm(text,path=""):
    try:return text.encode("latin-1").decode("utf-8","strict")
    except (UnicodeError,AttributeError):_invalid(path,"utf8")


def _json_node_value(node):
    from .stdlib import JsonNode
    if not isinstance(node,JsonNode):return node
    if node.kind=="null":return None
    if node.kind=="bool":return node.value
    if node.kind in ("int","float"):return node.value
    if node.kind=="string":return JsonText(node.value)
    if node.kind=="array":return [_json_node_value(v) for v in node.array]
    if node.kind=="object":return {JsonText(m.key):_json_node_value(m.value) for m in node.members}
    _invalid("","handle")

def to_json_value(value,path=""):
    if value is None or isinstance(value,DryNull):return None
    if isinstance(value,ObjectRef):
        obj=value.value
        try:
            from .stdlib import Collection,JsonNode
            if isinstance(obj,Collection): value=obj.value
            elif isinstance(obj,JsonNode): value=_json_node_value(obj)
            else:_invalid(path,"handle")
        except ImportError:_invalid(path,"handle")
    if isinstance(value,JsonText):return str(value)
    if type(value) is bool:return value
    if type(value) is int:
        if abs(value)>SAFE_INTEGER:_invalid(path,"unsafe_integer")
        return value
    if type(value) is float:
        if not math.isfinite(value):_invalid(path,"nonfinite")
        if value.is_integer() and abs(value)>SAFE_INTEGER:_invalid(path,"unsafe_integer")
        return 0.0 if value==0 else value
    if type(value) is str:return _decode_vm(value,path)
    if isinstance(value,(list,tuple)):
        return [to_json_value(item,_pointer(path,i)) for i,item in enumerate(value)]
    if isinstance(value,dict):
        result={}
        for key,item in value.items():
            if not isinstance(key,str):_invalid(path,"object key")
            text=str(key) if isinstance(key,JsonText) else _decode_vm(key,path)
            result[text]=to_json_value(item,_pointer(path,text))
        return result
    _invalid(path,"handle")


def _serialize_json(value):
    def encode(v):
        if v is None:return "null"
        if type(v) is bool:return "true" if v else "false"
        if type(v) is int:return str(v)
        if type(v) is float:return format_frame_float(v)
        if isinstance(v,str):return quote_json(str(v))
        if isinstance(v,list):return "["+",".join(encode(x) for x in v)+"]"
        if isinstance(v,dict):return "{"+",".join(quote_json(str(k))+":"+encode(x) for k,x in v.items())+"}"
        raise HostError("lmcode return: invalid JSON value at : handle")
    return encode(value)

def stringify(value):return _serialize_json(to_json_value(value))


def _kind(value):
    if value is None:return "null"
    if type(value) is bool:return "bool"
    if type(value) is int:return "int" if abs(value)<=SAFE_INTEGER else "unsafe int"
    if type(value) is float:
        if not math.isfinite(value):return "nonfinite"
        return "int" if value.is_integer() and abs(value)<=SAFE_INTEGER else "unsafe int" if value.is_integer() else "float"
    if type(value) is str:return "string"
    if isinstance(value,list):return "array"
    if isinstance(value,dict):return "object"
    return "handle"


class ResultContract:
    def __init__(self,type_name="",nullable=False):self.type=type_name;self.nullable=nullable
    @classmethod
    def from_schema(cls,raw):
        try: schema=json.loads(raw.decode("utf-8","strict"))
        except Exception as error:raise LmcodeError("LOAD_BAD_SCHEMA","lmcode result contract: "+str(error))
        def bad(message):raise LmcodeError("LOAD_BAD_SCHEMA","lmcode result contract: "+message)
        if not isinstance(schema,dict):bad("schema must be an object")
        if schema.get("dsl.schema")!=2:bad("requires schema 2")
        result=schema.get("result")
        if result is None:return cls()
        if not isinstance(result,dict):bad("result must be an object")
        for key in result:
            if key not in ("type","nullable"):bad("unknown key "+key)
        type_name=result.get("type")
        if not isinstance(type_name,str):bad("type must be a string")
        if type_name not in SUPPORTED:bad("unknown type "+type_name)
        if type_name=="null" and "nullable" in result:bad("type null forbids nullable")
        nullable=result.get("nullable",False)
        if type(nullable) is not bool:bad("nullable must be bool")
        return cls(type_name,nullable)
    def validate_source(self,value):
        if not self.type or self.type=="Json" or value is None:return
        actual=value.type_name if isinstance(value,ObjectRef) else "null" if isinstance(value,DryNull) else "void" if value is None else "int" if type(value) is int else "float" if type(value) is float else "bool" if type(value) is bool else "string" if type(value) is str else "handle"
        if actual=="void":actual="null"
        if actual==self.type or actual=="int" and self.type=="float" or actual=="IntList" and self.type=="FloatList" or actual=="IntMap" and self.type=="FloatMap":return
        _mismatch("",self.type,actual)
    def validate(self,value,path=""):
        if not self.type:return
        kind=_kind(value)
        if kind=="null":
            if self.nullable or self.type=="null":return
            _mismatch(path,self.type,"null")
        if self.type=="Json" or self.type=="int" and kind=="int" or self.type=="float" and kind in ("float","int") or self.type=="bool" and kind=="bool" or self.type=="string" and kind=="string":return
        is_list=self.type in ("StrList","IntList","FloatList");is_map=self.type in ("StrMap","IntMap","FloatMap")
        if is_list and isinstance(value,list) or is_map and isinstance(value,dict):
            element="string" if self.type.startswith("Str") else "int" if self.type.startswith("Int") else "float"
            items=enumerate(value) if is_list else value.items()
            for key,item in items:
                item_kind=_kind(item)
                if element=="float" and item_kind in ("float","int"):continue
                if element=="int" and item_kind=="int":continue
                if element=="string" and item_kind=="string":continue
                _mismatch(_pointer(path,key),element,item_kind)
            return
        _mismatch(path,self.type,kind)


def _mismatch(path,expected,actual):raise HostError("lmcode return: result type mismatch at "+path+": expected "+expected+"; got "+actual)


class ResultSink:
    def __init__(self,contract=None):self.contract=contract or ResultContract();self.root=None;self.sealed=False
    def _writable(self):
        if self.sealed:raise HostError("lmcode return: result sink is sealed")
    def reset(self):self._writable();self.root=None
    def set(self,value):
        self._writable();self.contract.validate_source(value);owned=to_json_value(value);self.contract.validate(owned);self.root=owned
    def set_null(self):self.set(None)
    def put(self,key,value):
        self._writable()
        if self.root is not None and not isinstance(self.root,dict):raise HostError("lmcode return: field assignment requires object or null")
        text=_decode_vm(key)
        self.contract.validate_source(value)
        owned=to_json_value(value,_pointer("",text))
        next_value=dict(self.root or {});next_value[text]=owned;self.contract.validate(next_value);self.root=next_value
    def put_null(self,key):self.put(key,None)
    def json(self):return _serialize_json(self.root)
    def complete(self):self._writable();self.contract.validate(self.root);self.sealed=True;return self.root


def _envelope_frame(payload):return "LMCODE_RETURN_BEGIN\n"+payload+"\nLMCODE_RETURN_END\n"
def success_frame(value,dry=False):
    payload="{\"ok\":true,\"result\":"+_serialize_json(value)+(",\"dry\":true" if dry else "")+"}"
    return _envelope_frame(payload)
def failure_frame(error,phase="run",part=None,dry=False):
    payload="{\"ok\":false,\"phase\":"+quote_json(phase)+",\"code\":"+quote_json(error.code)+",\"message\":"+quote_json(error.message)
    if error.line:payload+=",\"line\":"+str(error.line)
    if error.column:payload+=",\"column\":"+str(error.column)
    if part is not None:payload+=",\"part\":"+str(part)
    if dry or getattr(error,"invocation_dry",False):payload+=",\"dry\":true"
    payload+="}"
    return _envelope_frame(payload)

