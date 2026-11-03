"""Canonical byte-oriented lmcode standard catalog (206 signatures)."""
from __future__ import annotations
import base64, binascii, heapq, json, math, os, pathlib, re, struct, sys
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Any
from .errors import HostError
from .registry import DrySlot, ObjectRef, Registry, dry, real

@dataclass
class JsonNumber:
    raw: str
    value: Any
    kind: str
@dataclass
class JsonMember:
    key: str
    raw_key: str
    value: Any
@dataclass
class JsonNode:
    kind: str
    value: Any = None
    raw: str = ""
    array: list = None
    members: list = None
    def __post_init__(self):
        if self.array is None: self.array=[]
        if self.members is None: self.members=[]
    def json_value(self): return _json_plain(self)

@dataclass
class Collection:
    type_name: str
    value: Any


def _obj(type_name, value): return ObjectRef(type_name, value, id(value))
def _vm_text(text): return text.encode("utf-8").decode("latin-1")
def _text(raw):
    try: return raw.encode("latin-1").decode("utf-8", "strict")
    except (UnicodeError, AttributeError): raise HostError("string is not valid UTF-8")
def _ascii_lower(s): return s.translate(str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"))
def _ascii_upper(s): return s.translate(str.maketrans("abcdefghijklmnopqrstuvwxyz","ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
def _kind(value):
    if isinstance(value,JsonNode): return value.kind
    if isinstance(value,Collection): return value.type_name
    if value is None: return "null"
    if type(value) is bool: return "bool"
    if type(value) is int: return "int"
    if type(value) is float: return "float"
    if type(value) is str: return "string"
    if isinstance(value,(list,dict)): return "array" if isinstance(value,list) else "object"
    return "handle"

def _json_quote(text): return json.dumps(text,ensure_ascii=False,separators=(",",":"))
def _write_json(node):
    if isinstance(node,JsonNumber): return node.raw
    if isinstance(node,JsonNode):
        if node.kind in ("null","bool"): return node.raw
        if node.kind in ("int","float","string"): return node.raw
        if node.kind=="array": return "["+",".join(_write_json(x) for x in node.array)+"]"
        if node.kind=="object": return "{"+",".join(m.raw_key+":"+_write_json(m.value) for m in node.members)+"}"
    if node is None: return "null"
    if type(node) is str:return _json_quote(node)
    if type(node) is bool:return "true" if node else "false"
    if type(node) in (int,float):return json.dumps(node,separators=(",",":"),allow_nan=False)
    if isinstance(node,list):return "["+",".join(_write_json(v) for v in node)+"]"
    if isinstance(node,dict):return "{"+",".join(_json_quote(k)+":"+_write_json(v) for k,v in node.items())+"}"
    raise HostError("json_parse: invalid JSON node")

def _json_plain(node):
    if isinstance(node,JsonNode):
        if node.kind=="null":return None
        if node.kind=="bool":return node.value
        if node.kind=="string":return node.value
        if node.kind in ("int","float"):return node.value
        if node.kind=="array":return [_json_plain(x) for x in node.array]
        if node.kind=="object":return OrderedDict((m.key,_json_plain(m.value)) for m in node.members)
    if isinstance(node,Collection): return _json_plain(node.value)
    if isinstance(node,list):return [_json_plain(x) for x in node]
    if isinstance(node,dict):return OrderedDict((k,_json_plain(v)) for k,v in node.items())
    return node

def _bytes_to_vm(raw): return raw.decode("latin-1")
def _vm_to_bytes(text):
    try:return text.encode("latin-1")
    except UnicodeEncodeError: raise HostError("string contains a code point outside the byte range")
def _number_json(raw,at):
    if not re.fullmatch(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?",raw): raise HostError("json_parse: invalid number at byte "+str(at))
    if "." not in raw and "e" not in raw.lower():
        try: value=int(raw)
        except ValueError: raise HostError("json_parse: integer out of range at byte "+str(at))
        if value<-(1<<63) or value>(1<<63)-1: raise HostError("json_parse: integer out of range at byte "+str(at))
        return JsonNode("int",value,raw)
    try:value=float(raw)
    except ValueError: raise HostError("json_parse: invalid number at byte "+str(at))
    if not math.isfinite(value): raise HostError("json_parse: number out of range at byte "+str(at))
    nonzero=any(c in "123456789" for c in raw.split("e")[0].split("E")[0])
    if value==0 and nonzero: raise HostError("json_parse: number underflow at byte "+str(at))
    return JsonNode("float",value,raw)

class _JsonParser:
    def __init__(self, raw): self.raw=raw; self.i=0
    def fail(self,what,at=None): raise HostError("json_parse: "+what+" at byte "+str(self.i if at is None else at))
    def ws(self):
        while self.i<len(self.raw) and self.raw[self.i] in " \t\r\n": self.i+=1
    def literal(self,word):
        if not self.raw.startswith(word,self.i):self.fail("invalid literal")
        self.i+=len(word)
    def hex4(self,at):
        if at+4>len(self.raw):self.fail("invalid Unicode escape",at)
        result=0
        for i in range(4):
            c=self.raw[at+i]
            if "0"<=c<="9":digit=ord(c)-48
            elif "a"<=c<="f":digit=ord(c)-87
            elif "A"<=c<="F":digit=ord(c)-55
            else:self.fail("invalid Unicode escape",at+i)
            result=(result<<4)|digit
        return result
    def string(self):
        start=self.i
        if self.i>=len(self.raw) or self.raw[self.i]!='"':self.fail("expected string")
        self.i+=1; decoded=[]
        while self.i<len(self.raw):
            c=self.raw[self.i];self.i+=1
            if c=='"':
                token=self.raw[start:self.i]
                try:text=bytes(ord(ch) for ch in decoded).decode("utf-8","strict")
                except UnicodeDecodeError:self.fail("invalid UTF-8",start)
                return text,token
            if ord(c)<0x20:self.fail("control byte in string",self.i-1)
            if c!='\\':decoded.append(c);continue
            if self.i>=len(self.raw):self.fail("unterminated escape",self.i)
            esc=self.raw[self.i];self.i+=1
            if esc in ('"','\\','/'):decoded.append(esc)
            elif esc=='b':decoded.append("\b")
            elif esc=='f':decoded.append("\f")
            elif esc=='n':decoded.append("\n")
            elif esc=='r':decoded.append("\r")
            elif esc=='t':decoded.append("\t")
            elif esc=='u':
                cp=self.hex4(self.i);self.i+=4
                if 0xd800<=cp<=0xdbff:
                    if self.i+6>len(self.raw) or self.raw[self.i:self.i+2]!="\\u":self.fail("unpaired high surrogate",self.i)
                    low=self.hex4(self.i+2)
                    if not 0xdc00<=low<=0xdfff:self.fail("unpaired high surrogate",self.i)
                    self.i+=6;cp=0x10000+((cp-0xd800)<<10)+(low-0xdc00)
                elif 0xdc00<=cp<=0xdfff:self.fail("unpaired low surrogate",self.i-4)
                decoded.extend(chr(cp).encode("utf-8").decode("latin-1"))
            else:self.fail("invalid escape",self.i-1)
        self.fail("unterminated string",self.i)
    def number(self):
        start=self.i
        if self.raw[self.i]=='-':self.i+=1
        if self.i>=len(self.raw) or not self.raw[self.i].isdigit() or ord(self.raw[self.i])>127:self.fail("invalid number")
        if self.raw[self.i]=='0':self.i+=1
        else:
            while self.i<len(self.raw) and self.raw[self.i].isdigit() and ord(self.raw[self.i])<128:self.i+=1
        is_float=False
        if self.i<len(self.raw) and self.raw[self.i]=='.':
            is_float=True;self.i+=1
            if self.i>=len(self.raw) or not self.raw[self.i].isdigit() or ord(self.raw[self.i])>127:self.fail("invalid number")
            while self.i<len(self.raw) and self.raw[self.i].isdigit() and ord(self.raw[self.i])<128:self.i+=1
        if self.i<len(self.raw) and self.raw[self.i] in 'eE':
            is_float=True;self.i+=1
            if self.i<len(self.raw) and self.raw[self.i] in '+-':self.i+=1
            if self.i>=len(self.raw) or not self.raw[self.i].isdigit() or ord(self.raw[self.i])>127:self.fail("invalid number")
            while self.i<len(self.raw) and self.raw[self.i].isdigit() and ord(self.raw[self.i])<128:self.i+=1
        token=self.raw[start:self.i]
        if not is_float:
            try:value=int(token)
            except ValueError:self.fail("integer out of range",start)
            if value<-(1<<63) or value>(1<<63)-1:self.fail("integer out of range",start)
            return JsonNode("int",value,token)
        try:value=float(token)
        except ValueError:self.fail("invalid number",start)
        if math.isinf(value):self.fail("nonfinite number",start)
        return JsonNode("float",value,token)
    def value(self,depth=0):
        self.ws()
        if self.i>=len(self.raw):self.fail("expected value")
        start=self.i;c=self.raw[self.i]
        if depth>=256 and c in "[{":self.fail("maximum depth exceeded")
        if c=='"':
            value,token=self.string();return JsonNode("string",value,token)
        if c=='{':
            self.i+=1;self.ws();members=[];seen=set()
            if self.i<len(self.raw) and self.raw[self.i]=='}':self.i+=1;return JsonNode("object",members=members)
            while True:
                self.ws()
                if self.i>=len(self.raw) or self.raw[self.i]!='"':self.fail("object key must be a string")
                key_at=self.i;key,raw_key=self.string()
                if key in seen:self.fail("duplicate object key",key_at)
                seen.add(key);self.ws()
                if self.i>=len(self.raw) or self.raw[self.i]!=':':self.fail("expected colon")
                self.i+=1;child=self.value(depth+1);members.append(JsonMember(key,raw_key,child));self.ws()
                if self.i<len(self.raw) and self.raw[self.i]=='}':self.i+=1;break
                if self.i>=len(self.raw) or self.raw[self.i]!=',':self.fail("expected comma")
                self.i+=1
            return JsonNode("object",members=members)
        if c=='[':
            self.i+=1;self.ws();items=[]
            if self.i<len(self.raw) and self.raw[self.i]==']':self.i+=1;return JsonNode("array",array=items)
            while True:
                items.append(self.value(depth+1));self.ws()
                if self.i<len(self.raw) and self.raw[self.i]==']':self.i+=1;break
                if self.i>=len(self.raw) or self.raw[self.i]!=',':self.fail("expected comma")
                self.i+=1
            return JsonNode("array",array=items)
        if c=='n':self.literal("null");return JsonNode("null",None,"null")
        if c=='t':self.literal("true");return JsonNode("bool",True,"true")
        if c=='f':self.literal("false");return JsonNode("bool",False,"false")
        if c=='-' or c.isdigit() and ord(c)<128:return self.number()
        self.fail("unexpected value")
    def parse(self):
        raw=_vm_to_bytes(self.raw)
        try:raw.decode("utf-8","strict")
        except UnicodeDecodeError as error:self.fail("invalid UTF-8",error.start)
        if raw.startswith(b"\xef\xbb\xbf"):self.fail("BOM is not allowed",0)
        node=self.value();self.ws()
        if self.i!=len(self.raw):self.fail("trailing input")
        return node

def _parse_json(raw): return _JsonParser(raw).parse()

def _index(type_name,method,index,length):
    if type(index) is not int or index<0 or index>=length:raise HostError(type_name+"."+method+": index out of range: "+str(index))
    return index

def _make_collection(type_name,value):return _obj(type_name,Collection(type_name,value))
def _wrap_int(value):
    value &= (1<<64)-1
    return value-(1<<64) if value&(1<<63) else value
def _float_equal(a,b):return a==b or (a==0.0 and b==0.0)

def _match_token(pattern,index,byte):
    c=pattern[index]
    if c=="\\" and index+1<len(pattern):return pattern[index+1]==byte,index+2
    if c=="?":return True,index+1
    if c!="[":return c==byte,index+1
    q=index+1; neg=q<len(pattern) and pattern[q]=="!"
    if neg:q+=1
    first=q; hit=False
    while q<len(pattern) and (pattern[q]!="]" or q==first):
        if pattern[q]=="\\" and q+1<len(pattern):q+=1
        low=pattern[q];q+=1
        if q+1<len(pattern) and pattern[q]=="-" and pattern[q+1]!="]":
            q+=1
            if pattern[q]=="\\" and q+1<len(pattern):q+=1
            high=pattern[q];q+=1
            if low<=high and low<=byte<=high:hit=True
        elif low==byte:hit=True
    if q<len(pattern):return (not hit if neg else hit),q+1
    return byte=="[",index+1

def _glob(text,pattern):
    i=j=0;star=-1;star_i=0
    while i<len(text):
        if j<len(pattern) and pattern[j]=="*":star=j;star_i=i;j+=1;continue
        if j<len(pattern):
            ok,next_j=_match_token(pattern,j,text[i])
            if ok:i+=1;j=next_j;continue
        if star<0:return False
        j=star+1;star_i+=1;i=star_i
    while j<len(pattern) and pattern[j]=="*":j+=1
    return j==len(pattern)

def _format_number(value):
    from .vm import _format_g15
    return _format_g15(value)

def _parse_int(raw):
    if not re.fullmatch(r"[+-]?[0-9]+",raw):return None
    try:value=int(raw)
    except ValueError:return None
    return value if -(1<<63)<=value<(1<<63) else None

def _parse_float(raw):
    if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?",raw):return None
    try:value=float(raw)
    except ValueError:return None
    if not math.isfinite(value):return None
    nonzero=any(c in "123456789" for c in raw.split("e")[0].split("E")[0])
    if value==0 and nonzero:return None
    return value

def _string_fn(name,args):
    a=args[0]
    if name=="str_len":return len(a)
    if name=="str_starts_with":return a.startswith(args[1])
    if name=="str_ends_with":return a.endswith(args[1])
    if name=="str_contains":return args[1] in a
    if name=="str_find":return a.find(args[1])
    if name=="str_substr":
        start=max(0,args[1]);count=args[2]
        if count<=0 or start>=len(a):return ""
        return a[start:start+count]
    if name=="str_lower":return _ascii_lower(a)
    if name=="str_upper":return _ascii_upper(a)
    if name=="str_trim":return a.strip(" \t\n\r\v\f")
    if name=="str_repeat":
        if args[1]<0:raise HostError("str_repeat: count must be nonnegative")
        return a*args[1]
    if name=="str_replace":return a if not args[1] else a.replace(args[1],args[2])
    if name=="str_split":
        if not args[1]:raise HostError("str_split: separator must not be empty")
        return _make_collection("StrList",a.split(args[1]))
    if name=="str_is_int":return _parse_int(a) is not None
    if name=="str_to_int":
        value=_parse_int(a);return 0 if value is None else value
    if name=="str_is_float":return _parse_float(a) is not None
    if name=="str_to_float":
        value=_parse_float(a);return 0.0 if value is None else value
    if name=="str_match":return _glob(a,args[1])
    if name=="str_base64_encode":return base64.b64encode(_vm_to_bytes(a)).decode("ascii")
    if name=="str_base64_decode":
        try:
            raw=base64.b64decode(a.encode("ascii"),validate=True)
            if base64.b64encode(raw).decode("ascii")!=a:raise ValueError()
            return _bytes_to_vm(raw)
        except Exception:raise HostError("str_base64_decode: invalid encoding")
    if name=="str_hex_encode":return _vm_to_bytes(a).hex()
    if name=="str_hex_decode":
        if len(a)%2 or not re.fullmatch(r"[0-9a-fA-F]*",a):raise HostError("str_hex_decode: invalid encoding")
        return _bytes_to_vm(bytes.fromhex(a))
    raise HostError("unsupported standard function "+name)

def _math_fn(name,args,params):
    x=args[0]
    if name=="math_abs":return _wrap_int(abs(x)) if params[0]=="int" else abs(x)
    if name=="math_min":
        a,b=args
        if params[0]=="float" and (math.isnan(a) or math.isnan(b)):return math.nan
        return min(a,b)
    if name=="math_max":
        a,b=args
        if params[0]=="float" and (math.isnan(a) or math.isnan(b)):return math.nan
        return max(a,b)
    if name=="math_floor":return x if params[0]=="int" else (x if x==0.0 else float(math.floor(x))) if math.isfinite(x) else x
    if name=="math_ceil":
        if params[0]=="int" or not math.isfinite(x) or x==0.0:return x
        out=float(math.ceil(x));return math.copysign(0.0,x) if out==0.0 and x<0 else out
    if name=="math_round":
        if params[0]=="int":return x
        if not math.isfinite(x):return x
        out=float(math.floor(x+0.5) if x>=0 else math.ceil(x-0.5))
        return math.copysign(0.0,x) if out==0.0 and x<0 else out
    if name=="math_sqrt":
        if params[0]=="int":
            if x<0:raise HostError("math_sqrt: integer argument must be nonnegative")
            return math.isqrt(x)
        try:return math.sqrt(x)
        except ValueError:return math.nan
    if name=="math_pow":
        y=args[1]
        if params[0]=="int":
            if y<0:raise HostError("math_pow: integer exponent must be nonnegative")
            return _wrap_int(pow(x,y,1<<64))
        if x==0.0 and y<0:
            return math.copysign(math.inf,x) if math.copysign(1.0,x)<0 and y.is_integer() and int(y)%2 else math.inf
        try:return math.pow(x,y)
        except ValueError:return math.nan
        except OverflowError:return math.copysign(math.inf,x) if x<0 and y.is_integer() and int(y)%2 else math.inf
    raise HostError("unsupported math function "+name)


def _file_path(path, function):
    try: raw=_vm_to_bytes(path)
    except HostError: raise HostError(function+": "+path+": invalid path")
    if b"\0" in raw:raise HostError(function+": "+path+": invalid path")
    if os.name=="nt":
        try:return raw.decode("utf-8","strict")
        except UnicodeDecodeError:raise HostError(function+": "+path+": invalid path")
    return raw

def _file_error(function,path,error):raise HostError(function+": "+path+": "+str(error))
def _regular(path,function,flags,content=None):
    native=_file_path(path,function)
    try:
        if os.path.exists(native) and not os.path.isfile(native):raise OSError("invalid argument")
        if function in ("file_read","file_lines"):
            with open(native,"rb") as f:return _bytes_to_vm(f.read())
        mode="wb" if function=="file_write" else "ab"
        with open(native,mode) as f:f.write(_vm_to_bytes(content));f.flush();os.fsync(f.fileno())
        return None
    except OSError as error:_file_error(function,path,error)

def _file_function(name,args):
    path=args[0]
    if name=="file_read":return _regular(path,name,0)
    if name=="file_write":return _regular(path,name,0,args[1])
    if name=="file_append":return _regular(path,name,0,args[1])
    native=_file_path(path,name)
    if name=="file_exists":
        try:return os.path.isfile(native)
        except OSError as error:_file_error(name,path,error)
    if name=="file_lines":
        raw=_regular(path,name,0);return _make_collection("StrList",raw.split("\n"))
    raise HostError("unsupported file function "+name)

def _function_impl(name,params,returns):
    if name in {"str_len","str_starts_with","str_ends_with","str_contains","str_find","str_substr","str_lower","str_upper","str_trim","str_repeat","str_replace","str_split","str_is_int","str_to_int","str_is_float","str_to_float","str_match","str_base64_encode","str_base64_decode","str_hex_encode","str_hex_decode"}:
        return lambda ctx,self_obj,args:_string_fn(name,args)
    if name.startswith("math_"):
        return lambda ctx,self_obj,args:_math_fn(name,args,params)
    if name.startswith("file_"):
        return lambda ctx,self_obj,args:_file_function(name,args)
    if name in {"str_list","int_list","float_list","str_map","int_map","float_map","str_stack","int_stack","float_stack","str_queue","int_queue","float_queue","str_pq","int_pq","float_pq"}:
        type_name=returns; initial=OrderedDict() if type_name.endswith("Map") else []
        return lambda ctx,self_obj,args:_make_collection(type_name,initial.copy() if isinstance(initial,OrderedDict) else list(initial))
    if name.endswith("_map"):
        type_name=returns
        return lambda ctx,self_obj,args:_make_collection(type_name,OrderedDict())
    if name.endswith("_stack") or name.endswith("_queue") or name.endswith("_pq"):
        type_name=returns
        return lambda ctx,self_obj,args:_make_collection(type_name,[])
    if name=="json_parse":
        return lambda ctx,self_obj,args:_obj("Json",_parse_json(args[0]))
    if name=="template_render":
        return lambda ctx,self_obj,args:_template_render(args[0],args[1])
    if name=="lmcode_return_set":
        def fn(ctx,self_obj,args):
            if ctx.result_sink is None:raise HostError("lmcode return: no result sink")
            ctx.result_sink.set(args[0]);return None
        return fn
    if name=="lmcode_return_put":
        def fn(ctx,self_obj,args):
            if ctx.result_sink is None:raise HostError("lmcode return: no result sink")
            ctx.result_sink.put(_text(args[0]),args[1]);return None
        return fn
    if name=="lmcode_return_null":
        def fn(ctx,self_obj,args):
            if ctx.result_sink is None:raise HostError("lmcode return: no result sink")
            ctx.result_sink.set(None);return None
        return fn
    if name=="lmcode_return_put_null":
        def fn(ctx,self_obj,args):
            if ctx.result_sink is None:raise HostError("lmcode return: no result sink")
            ctx.result_sink.put(_text(args[0]),None);return None
        return fn
    raise RuntimeError("no standard implementation for "+name+str(params)+" -> "+returns)

def _list_value(receiver):
    if not isinstance(receiver.value,Collection):raise HostError("invalid collection handle")
    return receiver.value.value

def _method_impl(owner,name,params,returns):
    if owner in ("StrList","IntList","FloatList"):
        def call(ctx,self_ref,args):
            values=_list_value(self_ref)
            if name=="len":return len(values)
            if name=="at":return values[_index(owner,"at",args[0],len(values))]
            if name=="set":values[_index(owner,"set",args[0],len(values))]=args[1];return self_ref
            if name=="add":values.append(args[0]);return self_ref
            if name=="clear":values.clear();return self_ref
            if name=="contains":
                if owner=="FloatList":return any(not math.isnan(v) and not math.isnan(args[0]) and ((v==0.0 and args[0]==0.0 and struct.pack(">d",v)==struct.pack(">d",args[0])) or v==args[0]) for v in values)
                return args[0] in values
            if name=="index_of":
                for i,value in enumerate(values):
                    match=(not math.isnan(value) and not math.isnan(args[0]) and ((value==0.0 and args[0]==0.0 and struct.pack(">d",value)==struct.pack(">d",args[0])) or value==args[0])) if owner=="FloatList" else value==args[0]
                    if match:return i
                return -1
            if name=="join":return args[0].join(values)
        return call
    if owner in ("StrMap","IntMap","FloatMap"):
        def call(ctx,self_ref,args):
            values=_list_value(self_ref)
            if name=="len":return len(values)
            if name=="has":return args[0] in values
            if name=="get":
                key=args[0]
                if key not in values:raise HostError(owner+".get: missing key")
                return values[key]
            if name=="get_or":return values.get(args[0],args[1])
            if name=="set":values[args[0]]=args[1];return self_ref
            if name=="key_at":return list(values.keys())[_index(owner,"key_at",args[0],len(values))]
            if name=="remove":return values.pop(args[0],None) is not None
            if name=="clear":values.clear();return self_ref
            if name=="keys":return _make_collection("StrList",list(values.keys()))
            if name=="values":return _make_collection(returns,list(values.values()))
        return call
    if owner in ("StrStack","IntStack","FloatStack","StrQueue","IntQueue","FloatQueue","StrPQ","IntPQ","FloatPQ"):
        queue=owner.endswith("Queue");pq=owner.endswith("PQ")
        def call(ctx,self_ref,args):
            values=_list_value(self_ref)
            if name=="len":return len(values)
            if name=="empty":return not values
            if name=="clear":values.clear();return self_ref
            if name=="push":
                value=args[0]
                if pq:
                    priority=args[1]
                    if not math.isfinite(priority):raise HostError(owner+".push: priority must be finite")
                    values.append((priority,len(values),value));values.sort(key=lambda x:(x[0],x[1]))
                else:values.append(value)
                return self_ref
            if name=="peek" or name=="pop":
                if not values:raise HostError(owner+"."+name+": empty")
                idx=0 if queue or pq else len(values)-1
                item=values[idx]
                if name=="pop":values.pop(idx)
                return item[2] if pq else item
            if name=="at":
                idx=_index(owner,"at",args[0],len(values))
                if pq:item=values[idx];return item[2]
                if not queue and owner.endswith("Stack"):idx=len(values)-1-idx
                return values[idx]
        return call
    if owner=="Json":
        def call(ctx,self_ref,args):
            node=self_ref.value
            if not isinstance(node,JsonNode):raise HostError("invalid Json handle")
            if name=="kind":return node.kind
            if name=="len":
                if node.kind not in ("array","object"):raise HostError("Json.len: expected array or object")
                return len(node.array) if node.kind=="array" else len(node.members)
            if name=="at":
                if node.kind!="array":raise HostError("Json.at: expected array")
                return _obj("Json",node.array[_index("Json","at",args[0],len(node.array))])
            if name=="get":
                if node.kind!="object":raise HostError("Json.get: expected object")
                key=_text(args[0])
                for member in node.members:
                    if member.key==key:return _obj("Json",member.value)
                raise HostError("Json.get: missing key")
            if name=="has":
                if node.kind!="object":raise HostError("Json.has: expected object")
                key=_text(args[0]);return any(m.key==key for m in node.members)
            if name=="keys":
                if node.kind!="object":raise HostError("Json.keys: expected object")
                return _make_collection("StrList",[_vm_text(m.key) for m in node.members])
            if name=="as_string":
                if node.kind!="string":raise HostError("Json.as_string: expected string")
                return _vm_text(node.value)
            if name=="as_int":
                if node.kind!="int":raise HostError("Json.as_int: expected int")
                return node.value
            if name=="as_float":
                if node.kind not in ("int","float"):raise HostError("Json.as_float: expected number")
                return float(node.value)
            if name=="as_bool":
                if node.kind!="bool":raise HostError("Json.as_bool: expected bool")
                return node.value
            if name=="to_json":return node.raw if node.kind in ("null","bool","int","float","string") else _write_json(node)
        return call
    raise RuntimeError("no standard method implementation for "+owner+"."+name+str(params)+" -> "+returns)

def register_std(registry: Registry) -> None:
    import pathlib
    schema_path=pathlib.Path(__file__).parent/"data"/"lmcode-std.schema.json"
    schema=json.loads(schema_path.read_text(encoding="utf-8"))
    def slot_for_function(name):
        if name in ("file_write","file_append"):return None
        if name in {"str_list","int_list","float_list","str_map","int_map","float_map","str_stack","int_stack","float_stack","str_queue","int_queue","float_queue","str_pq","int_pq","float_pq"}:return None
        return dry(real)
    for name,overloads in schema.get("functions",{}).items():
        for declaration in overloads:
            params=declaration.get("params",[]); returns=declaration.get("returns","void")
            slot=slot_for_function(name)
            allow_null=name in {"lmcode_return_set","lmcode_return_put","lmcode_return_put_null"}
            registry.function(name,params,returns,_function_impl(name,params,returns),slot,_std=True,_raw=True,_allow_dry_null=allow_null)
    for owner,definition in schema.get("types",{}).items():
        for name,overloads in definition.get("methods",{}).items():
            for declaration in overloads:
                params=declaration.get("params",[]);returns=declaration.get("returns","void")
                registry.method(owner,name,params,returns,_method_impl(owner,name,params,returns),dry(real),_std=True,_raw=True)
    registry.std_enabled=True

def clear_run_objects(context): return None

def register_testing(registry: Registry, writer=None) -> None:
    import sys
    sink=writer if writer is not None else sys.stdout
    def print_value(ctx,self_obj,args):
        data=_vm_to_bytes(args[0])+b"\n"
        try:sink.write(data)
        except TypeError:sink.write(_text(args[0])+"\n")
        return None
    registry.function("print",["string"],"void",print_value,None,_std=False,_raw=True)
    def assert_close(ctx,self_obj,args):
        actual,expected,tolerance=args
        if not (abs(actual-expected)<=tolerance):
            raise HostError("assert_close failed: "+_format_number(actual)+" vs "+_format_number(expected)+" (tol "+_format_number(tolerance)+")")
        return None
    registry.function("assert_close",["float","float","float"],"void",assert_close,None,_raw=True)

_TEMPLATE_PATH=re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:[.][A-Za-z_][A-Za-z0-9_]*|\[[0-9]+\])*")

def _json_lookup(context,locals_,path):
    parts=re.findall(r"[A-Za-z_][A-Za-z0-9_]*|\[[0-9]+\]",path)
    if not parts:raise HostError("template_render: missing variable "+path)
    if parts[0] in locals_:node=locals_[parts[0]];parts=parts[1:]
    else:node=context
    for part in parts:
        if part.startswith("["):
            index=int(part[1:-1])
            if node.kind!="array" or index>=len(node.array) or str(index)!=part[1:-1]:raise HostError("template_render: missing variable "+path)
            node=node.array[index]
        else:
            if node.kind!="object":raise HostError("template_render: missing variable "+path)
            match=next((m.value for m in node.members if m.key==part),None)
            if match is None:raise HostError("template_render: missing variable "+path)
            node=match
    return node

def _template_parse(source,position=0,mode="",depth=0):
    if depth>256:raise HostError("template_render: maximum nesting exceeded")
    nodes=[];literal=[]
    def flush():
        if literal:nodes.append(("text","".join(literal)));literal.clear()
    while position<len(source):
        rest=source[position:]
        if mode=="loop" and rest.startswith("}>"):flush();return nodes,"",position+2
        if mode=="loop" and rest.startswith("};"):
            match=re.match(r'^};[ ]*separator[ ]*=("(?:[^"\\]|\\.)*")>',rest)
            if not match:raise HostError("template_render: invalid loop separator")
            try:separator=json.loads(match.group(1))
            except ValueError:raise HostError("template_render: invalid loop separator")
            flush();return nodes,separator,position+len(match.group(0))
        if rest.startswith("<<"):literal.append("<");position+=2;continue
        if rest.startswith("<else>") or rest.startswith("<endif>"):
            token="else" if rest.startswith("<else>") else "endif"
            if mode not in ("if","else") or mode=="else" and token=="else":raise HostError("template_render: unexpected conditional delimiter")
            flush();return nodes,token,position+(6 if token=="else" else 7)
        conditional=re.match(r'^<if\(('+_TEMPLATE_PATH.pattern+r')\)>',rest)
        if conditional:
            flush();path=conditional.group(1);position+=len(conditional.group(0));body,end,position=_template_parse(source,position,"if",depth+1);other=[]
            if end=="else":other,_,position=_template_parse(source,position,"else",depth+1)
            nodes.append(("if",path,body,other));continue
        head=re.match(r'^<('+_TEMPLATE_PATH.pattern+r')(?::\{([A-Za-z_][A-Za-z0-9_]*)\||>)',rest)
        if not head:literal.append(source[position]);position+=1;continue
        flush();path,item=head.group(1),head.group(2);position+=len(head.group(0))
        if item:
            if item=="index":raise HostError("template_render: index is reserved")
            body,separator,position=_template_parse(source,position,"loop",depth+1);nodes.append(("loop",path,item,body,_vm_text(separator)))
        else:nodes.append(("value",path))
    if mode:raise HostError("template_render: unterminated block")
    flush();return nodes,"",position

def _template_value(node):
    if node.kind=="string":return _vm_text(node.value)
    return _vm_text(_write_json(node))

def _template_eval(nodes,context,locals_,out):
    for node in nodes:
        if node[0]=="text":out.append(node[1]);continue
        if node[0]=="value":out.append(_template_value(_json_lookup(context,locals_,node[1])));continue
        if node[0]=="if":
            value=_json_lookup(context,locals_,node[1])
            if value.kind!="bool":raise HostError("template_render: condition requires a bool: "+node[1])
            _template_eval(node[2] if value.value else node[3],context,locals_,out);continue
        _,path,item,body,separator=node
        value=_json_lookup(context,locals_,path)
        if value.kind!="array":raise HostError("template_render: loop requires a list: "+path)
        for index,child in enumerate(value.array):
            if index:out.append(separator)
            scope=dict(locals_);scope[item]=child;scope["index"]=JsonNode("int",index,str(index))
            _template_eval(body,context,scope,out)

def _template_render(source,context):
    if isinstance(context,ObjectRef):context=context.value
    if not isinstance(context,JsonNode) or context.kind!="object":raise HostError("template_render: context must be an object")
    nodes,_,pos=_template_parse(source)
    if pos!=len(source):raise HostError("template_render: trailing template data")
    out=[];_template_eval(nodes,context,{},out);return "".join(out)
