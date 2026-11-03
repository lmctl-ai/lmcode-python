"""Synchronous stack VM for verified bytecode v6."""
from __future__ import annotations
import math
import struct
from typing import Any, List, Optional
from .binary import Reader
from .errors import HostError, LmcodeError, RunError
from .loader import Program, Region
from .registry import Context, ObjectRef, Registry

UNSET = object()


class DryNull:
    __slots__ = ("type_name",)
    def __init__(self, type_name: str): self.type_name = type_name


def kind(value: Any) -> str:
    if value is None: return "void"
    if isinstance(value, DryNull): return "dry null"
    if isinstance(value, ObjectRef): return "object"
    if type(value) is bool: return "bool"
    if type(value) is int: return "int"
    if type(value) is float: return "float"
    if type(value) is str: return "string"
    return "object"


def _checked_int(value: Any, what: str) -> int:
    if type(value) is not int: raise RunError("RUN_ERROR", what + " applied to " + kind(value))
    return value


def _checked_float(value: Any, what: str) -> float:
    if type(value) is not float: raise RunError("RUN_ERROR", what + " applied to " + kind(value))
    return value


def _wrap(value: int) -> int:
    value &= (1 << 64) - 1
    return value - (1 << 64) if value & (1 << 63) else value


def _trunc_div(a: int, b: int) -> int:
    if b == 0: raise RunError("RUN_ERROR", "int division by zero")
    if a == -(1 << 63) and b == -1: return -(1 << 63)
    quotient = abs(a) // abs(b)
    return -quotient if (a < 0) != (b < 0) else quotient


def _trunc_rem(a: int, b: int) -> int:
    if b == 0: raise RunError("RUN_ERROR", "int modulo by zero")
    return a - _trunc_div(a, b) * b


def _float_div(a: float, b: float) -> float:
    if b != 0.0: return a / b
    if a == 0.0 or math.isnan(a): return math.nan
    return math.copysign(math.inf, a * math.copysign(1.0, b))


def _format_g15(value: float) -> str:
    if math.isnan(value): return "nan"
    if math.isinf(value): return "inf" if value > 0 else "-inf"
    if value == 0.0: return "-0" if math.copysign(1.0, value) < 0 else "0"
    # Python's format uses the same correctly-rounded binary64 conversion as C %.15g.
    return format(value, ".15g")


def _math(fn_id: int, stack: list) -> None:
    if fn_id in (0,1,2,3,4,10,11,12,13):
        x = stack.pop()
        if type(x) is not float: raise RunError("RUN_ERROR", "math operand is not a float")
        if fn_id == 0:
            try: value = math.sin(x)
            except ValueError: value = math.nan
        elif fn_id == 1:
            try: value = math.cos(x)
            except ValueError: value = math.nan
        elif fn_id == 2:
            try: value = math.sqrt(x)
            except ValueError: value = math.nan
        elif fn_id == 3: value = abs(x)
        elif fn_id == 4: value = math.floor(x) if math.isfinite(x) else x
        elif fn_id == 10:
            t = min(max(x, 0.0), 1.0); value = t * t * (3.0 - 2.0 * t)
        elif fn_id == 11:
            t = min(max(x, 0.0), 1.0); value = t * t
        elif fn_id == 12:
            t = min(max(x, 0.0), 1.0); d = 1.0 - t; value = 1.0 - d * d
        else:
            if math.isnan(x): value = 0
            elif x >= 9223372036854775808.0: value = (1 << 63) - 1
            elif x <= -9223372036854775808.0: value = -(1 << 63)
            else: value = int(x)
        stack.append(value if fn_id == 13 else float(value)); return
    if fn_id == 14:
        stack.append(_wrap(abs(_checked_int(stack.pop(), "abs")))); return
    if fn_id in (5,6,7,15,16):
        b, a = stack.pop(), stack.pop()
        if fn_id <= 7:
            x, y = _checked_float(a, "math"), _checked_float(b, "math")
            if fn_id == 5:
                try: out = math.pow(x,y)
                except (ValueError, OverflowError): out = math.nan if x < 0 and not y.is_integer() else math.inf
            elif fn_id == 6: out = math.nan if math.isnan(x) or math.isnan(y) else min(x,y)
            else: out = math.nan if math.isnan(x) or math.isnan(y) else max(x,y)
        else:
            x, y = _checked_int(a, "math"), _checked_int(b, "math")
            out = min(x,y) if fn_id == 15 else max(x,y)
        stack.append(out); return
    if fn_id in (8,9,17):
        hi, lo, x = stack.pop(), stack.pop(), stack.pop()
        if fn_id == 17:
            x, lo, hi = _checked_int(x,"clamp"), _checked_int(lo,"clamp"), _checked_int(hi,"clamp")
            stack.append(max(x,lo).min(hi) if False else min(max(x,lo),hi)); return
        x, lo, hi = _checked_float(x,"math"), _checked_float(lo,"math"), _checked_float(hi,"math")
        if fn_id == 8: stack.append(min(max(x,lo),hi))
        else: stack.append(x + (lo - x) * hi)
        return
    raise RunError("RUN_ERROR", "unknown MATH function " + str(fn_id))


def _dummy(return_type: str) -> Any:
    if return_type == "void": return None
    if return_type == "bool": return True
    if return_type == "int": return 0
    if return_type == "float": return 0.0
    if return_type == "string": return ""
    if return_type == "null": return None
    if return_type in {"StrList","IntList","FloatList","StrMap","IntMap","FloatMap","StrStack","IntStack","FloatStack","StrQueue","IntQueue","FloatQueue","StrPQ","IntPQ","FloatPQ"}:
        from .stdlib import Collection
        value=Collection(return_type,{} if return_type.endswith("Map") else [])
        return ObjectRef(return_type,value,id(value))
    return DryNull(return_type)


def _host_text(value: str) -> str:
    try: return value.encode("latin-1").decode("utf-8", "strict")
    except (UnicodeEncodeError, UnicodeDecodeError) as error: raise HostError("string is not valid UTF-8: " + str(error))

def _host_arg(value: Any, raw: bool, preserve_objects: bool) -> Any:
    if isinstance(value,ObjectRef) and not preserve_objects:return value.value
    return _host_text(value) if type(value) is str and not raw else value

def _host_result(value: Any, raw: bool, return_type: str, registry: Registry) -> Any:
    if isinstance(value,ObjectRef):return value
    if raw:return value.decode("latin-1") if type(value) is bytes else value
    if type(value) is str:return value.encode("utf-8").decode("latin-1")
    if type(value) is bytes:return value.decode("latin-1")
    if return_type not in ("void","null","int","integer","int64","float","double","number","string","bool") and return_type not in registry.enum_types:
        return ObjectRef(return_type,value,id(value))
    return value

def _host_failure(error: BaseException) -> HostError:
    if isinstance(error,MemoryError):return HostError("memory allocation failed")
    if isinstance(error,RecursionError):return HostError("maximum recursion depth exceeded")
    return HostError(str(error))

def _call_function(binding, ctx: Context, args: List[Any], registry: Registry) -> Any:
    if ctx.dry_mode and binding.dry_callback is None and not binding.dry_uses_real:
        return _dummy(binding.signature.returns)
    if ctx.dry_mode and not binding.allow_dry_null and any(isinstance(v, DryNull) for v in args):
        raise HostError("dry null cannot be passed to a host callback")
    callback = binding.dry_callback if ctx.dry_mode and binding.dry_callback is not None else binding.callback
    try:
        result = callback(ctx, None, [_host_arg(value,binding.raw_strings,binding.is_std) for value in args])
        result = _host_result(result,binding.raw_strings,binding.signature.returns,registry)
    except LmcodeError:
        raise
    except (MemoryError,RecursionError) as error:
        raise _host_failure(error) from None
    except Exception as error:
        raise _host_failure(error) from None
    if ctx.dry_mode and not binding.dry_uses_real and kind(result) != _expected_kind(binding.signature.returns):
        raise HostError("dry callback for " + binding.signature.returns + " returned " + kind(result))
    return result


def _expected_kind(type_name: str) -> str:
    return {"void":"void","null":"void","bool":"bool","int":"int","float":"float","string":"string"}.get(type_name,"object")


def _call_method(binding, ctx: Context, receiver: Any, args: List[Any], registry: Registry) -> Any:
    if isinstance(receiver, DryNull):
        if not ctx.dry_mode or receiver.type_name != binding.owner:
            raise HostError("invalid dry null provenance in method receiver")
        if binding.dry_callback is None and not binding.dry_uses_real:
            return _dummy(binding.signature.returns)
        raise HostError("method " + binding.owner + "." + binding.name + " requires a concrete receiver after dry null")
    if not isinstance(receiver, ObjectRef) or receiver.type_name != binding.owner:
        receiver_kind=receiver.type_name if isinstance(receiver,ObjectRef) else kind(receiver)
        raise RunError("RUN_ERROR", "method " + binding.owner + "." + binding.name + " called on a " + receiver_kind)
    if ctx.dry_mode and binding.dry_callback is None and not binding.dry_uses_real:
        return _dummy(binding.signature.returns)
    if ctx.dry_mode and any(isinstance(v, DryNull) for v in args):
        raise HostError("dry null cannot be passed to a host callback")
    callback = binding.dry_callback if ctx.dry_mode and binding.dry_callback is not None else binding.callback
    try:
        result = callback(ctx, receiver if binding.is_std else receiver.value, [_host_arg(value,binding.raw_strings,binding.is_std) for value in args])
        return_type=binding.owner if binding.signature.returns=="self" else binding.signature.returns
        result = _host_result(result,binding.raw_strings,return_type,registry)
    except LmcodeError:
        raise
    except (MemoryError,RecursionError) as error:
        raise _host_failure(error) from None
    except Exception as error:
        raise _host_failure(error) from None
    if ctx.dry_mode and not binding.dry_uses_real and kind(result) != _expected_kind(binding.signature.returns):
        raise HostError("dry callback for " + binding.signature.returns + " returned " + kind(result))
    return result


def _execute(program: Program, region: Region, context: Context, registry: Registry, args: List[Any], capture: bool) -> Any:
    generation=registry.begin_run()
    if registry.result_sink is not None: context.result_sink=registry.result_sink
    if registry.std_enabled:
        from .stdlib import clear_run_objects
        clear_run_objects(context)
    locals_ = [UNSET] * len(region.locals)
    for i, value in enumerate(args): locals_[i] = value
    stack: List[Any] = []
    reader = Reader(region.code, "RUN_ERROR")
    try:
        while not reader.done():
            fault_pc = reader.pos
            halted = False
            try:
                opcode = reader.u8()
                from .loader import OPS
                op = OPS.get(opcode)
                if op is None: raise RunError("RUN_ERROR", "unknown opcode " + str(opcode))
                if op == "PUSH_INT": stack.append(reader.i64())
                elif op == "PUSH_FLOAT": stack.append(struct.unpack(">d", struct.pack(">II", reader.u32(), reader.u32()))[0])
                elif op == "PUSH_STR": stack.append(program.constants[reader.u32()].decode("latin-1"))
                elif op == "PUSH_BOOL": stack.append(reader.u8() != 0)
                elif op == "LOAD_LOCAL":
                    slot = reader.u16(); value = locals_[slot]
                    if value is UNSET: raise RunError("RUN_ERROR", "local slot " + str(slot) + " read before assignment")
                    stack.append(value)
                elif op == "STORE_LOCAL": locals_[reader.u16()] = stack.pop()
                elif op == "LOAD_CTX":
                    name, type_name = program.contexts[reader.u16()]
                    value = context.values.get(name, UNSET)
                    if value is UNSET: raise RunError("RUN_ERROR", "context variable '" + name + "' was not provided by the host for this run")
                    if not isinstance(value, ObjectRef): value = ObjectRef(type_name, value, id(value))
                    if value.type_name != type_name: raise RunError("RUN_ERROR", "context variable '" + name + "' is a " + value.type_name + ", expected " + type_name)
                    stack.append(value)
                elif op in ("CALL_FN", "CALL_METHOD"):
                    index, argc = reader.u16(), reader.u8()
                    values = [stack.pop() for _ in range(argc)][::-1]
                    imp = program.imports[index]
                    if op == "CALL_FN":
                        binding = registry.functions[imp.canonical]
                        result = _call_function(binding, context, values, registry)
                    else:
                        receiver = stack.pop()
                        binding = registry.method_by_signature(imp.canonical)
                        result = _call_method(binding, context, receiver, values, registry)
                    if result is not None: stack.append(result)
                elif op in ("EQ", "NE"):
                    b, a = stack.pop(), stack.pop()
                    if kind(a) != kind(b): raise RunError("RUN_ERROR", "cannot compare " + kind(a) + " with " + kind(b))
                    if isinstance(a, ObjectRef) and isinstance(b, ObjectRef): equal = a.value is b.value
                    elif isinstance(a, DryNull) and isinstance(b, DryNull): equal = a.type_name == b.type_name
                    else: equal = a == b
                    stack.append(equal if op == "EQ" else not equal)
                elif op in ("ADD_I","SUB_I","MUL_I","DIV_I","MOD_I"):
                    b, a = stack.pop(), stack.pop(); x=_checked_int(a,"int operator"); y=_checked_int(b,"int operator")
                    if op == "ADD_I": out = x+y
                    elif op == "SUB_I": out = x-y
                    elif op == "MUL_I": out = x*y
                    elif op == "DIV_I": out = _trunc_div(x,y)
                    else: out = _trunc_rem(x,y)
                    stack.append(_wrap(out))
                elif op in ("ADD_F","SUB_F","MUL_F","DIV_F"):
                    b, a = stack.pop(), stack.pop(); x=_checked_float(a,"float operator"); y=_checked_float(b,"float operator")
                    if op == "ADD_F": out=x+y
                    elif op == "SUB_F": out=x-y
                    elif op == "MUL_F": out=x*y
                    else: out=_float_div(x,y)
                    stack.append(out)
                elif op in ("LT_I","LE_I","GT_I","GE_I","LT_F","LE_F","GT_F","GE_F"):
                    b,a=stack.pop(),stack.pop(); integer=op.endswith("_I")
                    x=_checked_int(a,"int operator") if integer else _checked_float(a,"float operator")
                    y=_checked_int(b,"int operator") if integer else _checked_float(b,"float operator")
                    stack.append({"LT_I":lambda:x<y,"LE_I":lambda:x<=y,"GT_I":lambda:x>y,"GE_I":lambda:x>=y,"LT_F":lambda:x<y,"LE_F":lambda:x<=y,"GT_F":lambda:x>y,"GE_F":lambda:x>=y}[op]())
                elif op == "NEG_I": stack.append(_wrap(-_checked_int(stack.pop(),"int negation")))
                elif op == "NEG_F": stack.append(-_checked_float(stack.pop(),"float negation"))
                elif op == "I2F": stack.append(float(_checked_int(stack.pop(),"float()")))
                elif op == "MATH": _math(reader.u8(), stack)
                elif op == "NOT":
                    value=stack.pop()
                    if type(value) is not bool: raise RunError("RUN_ERROR", "! applied to a " + kind(value))
                    stack.append(not value)
                elif op in ("JUMP","JUMP_IF_FALSE","JUMP_IF_TRUE"):
                    rel=reader.i32()
                    take=True
                    if op != "JUMP":
                        condition=stack.pop()
                        if type(condition) is not bool: raise RunError("RUN_ERROR", "condition is a " + kind(condition) + ", not a bool")
                        take=condition == (op == "JUMP_IF_TRUE")
                    if take: reader.pos = reader.pos + rel
                elif op == "FOR_RANGE":
                    counter,end,rel=reader.u16(),reader.u16(),reader.i32(); end_value=stack.pop(); start=stack.pop()
                    start=_checked_int(start,"range start"); end_value=_checked_int(end_value,"range end")
                    locals_[counter]=_wrap(start); locals_[end]=_wrap(end_value)
                    if start >= end_value: reader.pos += rel
                elif op == "FOR_NEXT":
                    _encoded_end=reader.u16(); rel=reader.i32(); counter,end=region.loop_pairs[fault_pc]
                    locals_[counter]=_wrap(_checked_int(locals_[counter],"range counter")+1)
                    if locals_[counter] < locals_[end]: reader.pos += rel
                elif op == "WHILE_BEGIN": pass
                elif op == "WHILE_TEST":
                    rel=reader.i32(); condition=stack.pop()
                    if type(condition) is not bool: raise RunError("RUN_ERROR", "condition is a " + kind(condition) + ", not a bool")
                    if not condition: reader.pos += rel
                elif op == "LOOP_BACK":
                    rel=reader.i32(); reader.pos += rel
                elif op == "DUP": stack.append(stack[-1])
                elif op == "POP": stack.pop()
                elif op == "HALT":
                    halted=True
                    return stack.pop() if capture else None
                elif op == "CONCAT":
                    b,a=stack.pop(),stack.pop()
                    if type(a) is not str or type(b) is not str: raise RunError("RUN_ERROR", "string + applied to " + kind(a) + " and " + kind(b))
                    stack.append(a+b)
                elif op == "I2S": stack.append(str(_checked_int(stack.pop(),"str(int)")))
                elif op == "F2S": stack.append(_format_g15(_checked_float(stack.pop(),"str(float)")))
                elif op == "B2S":
                    value=stack.pop()
                    if type(value) is not bool: raise RunError("RUN_ERROR", "str(bool) applied to " + kind(value))
                    stack.append("true" if value else "false")
                else: raise RunError("RUN_ERROR", "unsupported opcode " + op)
            except LmcodeError as error:
                line = next((item for item in reversed(region.lines) if item.pc <= fault_pc), None)
                if line is not None: error.locate(line.line, line.column)
                raise
            except (IndexError, KeyError, struct.error) as error:
                raise RunError("RUN_ERROR", "invalid runtime state: " + str(error))
        raise RunError("RUN_ERROR", "code ended without HALT")
    finally:
        if registry.std_enabled:
            from .stdlib import clear_run_objects
            try:clear_run_objects(context)
            finally:registry.end_run(generation)

def execute(program: Program, region: Region, context: Context, registry: Registry, args: List[Any], capture: bool) -> Any:
    try:
        return _execute(program,region,context,registry,args,capture)
    except (MemoryError,RecursionError) as error:
        registry.end_run(registry._run_generation)
        raise _host_failure(error) from None
