"""Bytecode v6 parser, registry binder, and structural verifier."""
from __future__ import annotations
from dataclasses import dataclass, field
import hashlib
from typing import Dict, List, Optional, Tuple
from .binary import Reader
from .errors import LoadError
from .registry import Registry

VERSION = 6
MAGIC = b"DSLB"
OPS = {
    0x01:"PUSH_INT",0x02:"PUSH_STR",0x03:"PUSH_BOOL",0x04:"LOAD_LOCAL",0x05:"STORE_LOCAL",0x06:"LOAD_CTX",
    0x07:"CALL_FN",0x08:"CALL_METHOD",0x09:"EQ",0x0A:"NE",0x0B:"NOT",0x0C:"JUMP",0x0D:"JUMP_IF_FALSE",
    0x0E:"JUMP_IF_TRUE",0x0F:"DUP",0x10:"POP",0x11:"HALT",0x12:"PUSH_FLOAT",0x13:"ADD_I",
    0x14:"SUB_I",0x15:"MUL_I",0x16:"DIV_I",0x17:"ADD_F",0x18:"SUB_F",0x19:"MUL_F",0x1A:"DIV_F",
    0x1B:"NEG_I",0x1C:"NEG_F",0x1D:"LT_I",0x1E:"LE_I",0x1F:"GT_I",0x20:"GE_I",0x21:"LT_F",
    0x22:"LE_F",0x23:"GT_F",0x24:"GE_F",0x25:"I2F",0x26:"CONCAT",0x27:"I2S",0x28:"F2S",
    0x29:"B2S",0x2F:"FOR_RANGE",0x31:"FOR_NEXT",0x32:"MATH",0x33:"MOD_I",0x34:"WHILE_BEGIN",
    0x35:"WHILE_TEST",0x36:"LOOP_BACK",
}


@dataclass(frozen=True)
class Local:
    type_name: str
    hidden: bool


@dataclass(frozen=True)
class Line:
    pc: int
    line: int
    column: int


@dataclass
class Instruction:
    pc: int
    op: str
    args: Tuple[int, ...]
    next_pc: int


@dataclass
class Region:
    locals: List[Local]
    max_stack: int
    code: bytes
    lines: List[Line]
    instructions: List[Instruction] = field(default_factory=list)
    by_pc: Dict[int, Instruction] = field(default_factory=dict)
    loop_pairs: Dict[int, Tuple[int, int]] = field(default_factory=dict)


@dataclass(frozen=True)
class Import:
    kind: str
    canonical: str
    owner: str = ""
    name: str = ""


@dataclass
class Entry:
    name: str
    annotation: str
    interface: str
    params: Tuple[str, ...]
    returns: str
    region: Region


@dataclass
class Program:
    constants: List[bytes]
    imports: List[Import]
    contexts: List[Tuple[str, str]]
    body: Region
    entries: List[Entry]
    schema_hash: bytes

    def run(self, context, registry):
        from .vm import execute
        execute(self, self.body, context, registry, [], False)

    def call(self, entry, context, registry, args):
        from .vm import execute
        selected = self.entries[entry] if type(entry) is int else next((e for e in self.entries if e.name == entry), None)
        if selected is None:
            from .errors import HostError
            raise HostError("call entry '" + str(entry) + "' not found")
        if len(args) != len(selected.params):
            from .errors import HostError
            raise HostError("call entry '" + selected.name + "' expects " + str(len(selected.params)) + " argument(s); found " + str(len(args)))
        return execute(self, selected.region, context, registry, list(args), selected.returns != "void")


def _fail(message: str, code: str = "LOAD_BAD_BYTECODE") -> None:
    raise LoadError(code, message)


def _utf8(value: bytes, what: str) -> str:
    try:
        return value.decode("utf-8", "strict")
    except UnicodeDecodeError:
        _fail(what + " is not valid UTF-8")


def _const(constants: List[bytes], index: int, what: str) -> str:
    if index >= len(constants):
        _fail(what + ": constant index " + str(index) + " out of range (" + str(len(constants)) + " constants)")
    return _utf8(constants[index], what + " constant " + str(index))


def _parse_interface(text: str) -> Optional[Tuple[Tuple[str, ...], str]]:
    if not text.startswith("interface ") or "(" not in text:
        return None
    name, tail = text[len("interface "):].split("(", 1)
    if ") -> " not in tail:
        return None
    args, returns = tail.split(") -> ", 1)
    ident = lambda x: bool(x) and (x[0].isalpha() or x[0] == "_") and all(c.isalnum() or c == "_" for c in x)
    if not ident(name) or not ident(returns):
        return None
    params = tuple(args.split(", ")) if args else ()
    if any(not ident(p) or p == "void" for p in params):
        return None
    return params, returns


def _read_region(reader: Reader, constants: List[bytes]) -> Region:
    nlocals = reader.u16()
    locals_: List[Local] = []
    for i in range(nlocals):
        type_name = _const(constants, reader.u32(), "local type")
        hidden = reader.u8()
        if hidden not in (0, 1):
            _fail("local " + str(i) + " hidden flag must be 0 or 1")
        locals_.append(Local(type_name, hidden == 1))
    max_stack = reader.u16()
    code = reader.bytes(reader.u32())
    line_count = reader.u32()
    lines: List[Line] = []
    for i in range(line_count):
        line = Line(reader.u32(), reader.u32(), reader.u16())
        if lines and line.pc < lines[-1].pc:
            _fail("line table is not sorted by pc at entry " + str(i))
        lines.append(line)
    return Region(locals_, max_stack, code, lines)


def _decode(region: Region, constants: List[bytes], context_count: int, import_count: int) -> None:
    reader = Reader(region.code)
    instructions: List[Instruction] = []
    structural_loops = []
    while not reader.done():
        pc = reader.pos
        opcode = reader.u8()
        op = OPS.get(opcode)
        if op is None:
            _fail("unknown opcode " + str(opcode) + " at offset " + str(pc))
        args: Tuple[int, ...] = ()
        if op == "PUSH_INT": args = (reader.i64(),)
        elif op == "PUSH_FLOAT": args = (reader.u32(), reader.u32())
        elif op == "PUSH_STR":
            idx = reader.u32()
            if idx >= len(constants): _fail("constant index " + str(idx) + " out of range (" + str(len(constants)) + " entries)")
            args = (idx,)
        elif op == "PUSH_BOOL":
            value = reader.u8()
            if value > 1: _fail("PUSH_BOOL operand must be 0 or 1")
            args = (value,)
        elif op in ("LOAD_LOCAL", "STORE_LOCAL"):
            idx = reader.u16()
            if idx >= len(region.locals): _fail("local slot index " + str(idx) + " out of range (" + str(len(region.locals)) + " entries)")
            if op == "STORE_LOCAL" and region.locals[idx].hidden:
                _fail("STORE_LOCAL at offset " + str(pc) + " writes compiler-owned loop local " + str(idx))
            args = (idx,)
        elif op == "LOAD_CTX":
            idx = reader.u16()
            if idx >= context_count: _fail("context index " + str(idx) + " out of range (" + str(context_count) + " entries)")
            args = (idx,)
        elif op in ("CALL_FN", "CALL_METHOD"):
            idx, argc = reader.u16(), reader.u8()
            if idx >= import_count: _fail("import index " + str(idx) + " out of range (" + str(import_count) + " entries)")
            args = (idx, argc)
        elif op == "MATH":
            fn_id = reader.u8()
            if fn_id > 17: _fail("unknown MATH function " + str(fn_id) + " at offset " + str(pc))
            args = (fn_id,)
        elif op in ("JUMP", "JUMP_IF_FALSE", "JUMP_IF_TRUE"):
            args = (reader.i32(),)
        elif op == "FOR_RANGE":
            args = (reader.u16(), reader.u16(), reader.i32())
            structural_loops.append(("range", pc))
        elif op == "FOR_NEXT":
            if not structural_loops or structural_loops[-1][0] != "range":
                _fail("FOR_NEXT at offset " + str(pc) + " has no matching FOR_RANGE")
            structural_loops.pop()
            args = (reader.u16(), reader.i32())
        elif op == "WHILE_BEGIN": structural_loops.append(("while", pc))
        elif op == "WHILE_TEST":
            if not structural_loops or structural_loops[-1][0] != "while":
                _fail("WHILE_TEST at offset " + str(pc) + " has no matching WHILE_BEGIN")
            args = (reader.i32(),)
        elif op == "LOOP_BACK":
            if not structural_loops or structural_loops[-1][0] != "while":
                _fail("LOOP_BACK at offset " + str(pc) + " has no matching WHILE_BEGIN")
            rel = reader.i32()
            opener = structural_loops[-1][1]
            if reader.pos + rel != opener:
                _fail("LOOP_BACK at offset " + str(pc) + " does not target its paired WHILE_BEGIN")
            structural_loops.pop(); args = (rel,)
        elif op == "HALT" and structural_loops:
            _fail("HALT inside loop")
        instructions.append(Instruction(pc, op, args, reader.pos))
    region.instructions = instructions
    region.by_pc = {i.pc: i for i in instructions}
    if any(line.pc >= len(region.code) for line in region.lines):
        line = next(line for line in region.lines if line.pc >= len(region.code))
        _fail("line table entry points at pc " + str(line.pc) + ", beyond the code")


def _declared_hint(registry: Registry, canonical: str) -> str:
    prefix = canonical.split("(", 1)[0]
    names = [sig for sig in registry.signatures() if sig.split("(", 1)[0] == prefix]
    return " (the host declares " + ", ".join(names) + ")" if names else ""


def load(bytecode: bytes, schema_bytes: bytes, registry: Registry) -> Program:
    if len(bytecode) < 4 or bytecode[:4] != MAGIC:
        _fail("not a DSL bytecode file: bad magic (expected 'DSLB')")
    reader = Reader(bytecode)
    reader.bytes(4)
    version = reader.u16()
    if version != VERSION:
        _fail("unsupported bytecode version " + str(version) + " (this runtime reads version " + str(VERSION) + ")")
    schema_hash = reader.bytes(32)
    expected_hash = hashlib.sha256(schema_bytes).digest()
    if schema_hash != expected_hash:
        _fail("schema mismatch: bytecode was compiled against schema sha256 " + schema_hash.hex() + ", the given schema has sha256 " + expected_hash.hex(), "LOAD_SCHEMA_MISMATCH")
    count = reader.u32()
    constants: List[bytes] = []
    for i in range(count):
        tag = reader.u8()
        if tag != 1: _fail("constant " + str(i) + " has unknown tag " + str(tag) + " (1 = string)")
        constants.append(reader.bytes(reader.u32()))
    imports: List[Import] = []
    for _ in range(reader.u16()):
        canonical = _const(constants, reader.u32(), "import")
        if canonical.startswith("fn "):
            if canonical not in registry.functions:
                _fail("import '" + canonical + "' is not provided by the host" + _declared_hint(registry, canonical), "LOAD_UNBOUND")
            imports.append(Import("function", canonical))
        elif canonical.startswith("method "):
            head = canonical[len("method "):].split("(", 1)[0]
            if "." not in head or registry.method_by_signature(canonical) is None:
                _fail("import '" + canonical + "' is not provided by the host" + _declared_hint(registry, canonical), "LOAD_UNBOUND")
            owner, name = head.split(".", 1)
            imports.append(Import("method", canonical, owner, name))
        else:
            _fail("import '" + canonical + "' is not provided by the host", "LOAD_UNBOUND")
    contexts: List[Tuple[str, str]] = []
    for _ in range(reader.u16()):
        name = _const(constants, reader.u32(), "context name")
        type_name = _const(constants, reader.u32(), "context type")
        provided = registry.contexts.get(name)
        if provided is None: _fail("context variable '" + name + "' is not declared by the host", "LOAD_UNBOUND")
        if provided != type_name: _fail("context variable '" + name + "' is declared as " + type_name + " by the bytecode, the host provides " + provided, "LOAD_UNBOUND")
        contexts.append((name, type_name))
    body = _read_region(reader, constants)
    entries: List[Entry] = []
    for _ in range(reader.u16()):
        name = _const(constants, reader.u32(), "entry name")
        if any(entry.name == name for entry in entries): _fail("duplicate entry name '" + name + "'")
        annotation = _const(constants, reader.u32(), "entry annotation")
        interface = _const(constants, reader.u32(), "entry interface")
        parsed = _parse_interface(interface)
        if parsed is None: _fail("entry '" + name + "': interface '" + interface + "' is not an interface signature")
        params, returns = parsed
        nparams = reader.u16()
        region = _read_region(reader, constants)
        if nparams != len(params): _fail("entry '" + name + "' declares " + str(nparams) + " parameter(s); " + interface + " has " + str(len(params)))
        if nparams > len(region.locals): _fail("entry '" + name + "': nparams " + str(nparams) + " exceeds nlocals " + str(len(region.locals)))
        for idx, expected in enumerate(params):
            if region.locals[idx].hidden: _fail("entry '" + name + "' parameter " + str(idx + 1) + " is hidden")
            if region.locals[idx].type_name != expected: _fail("entry '" + name + "' parameter " + str(idx + 1) + " has type " + region.locals[idx].type_name + "; the interface expects " + expected)
        entries.append(Entry(name, annotation, interface, params, returns, region))
    if not reader.done(): _fail("bytecode has " + str(len(bytecode) - reader.pos) + " trailing byte(s) after the entries")
    program = Program(constants, imports, contexts, body, entries, schema_hash)
    for region, returns in [(body, None)] + [(entry.region, entry.returns) for entry in entries]:
        _decode(region, constants, len(contexts), len(imports))
        _verify(program, registry, region)
        _verify_stack(program, registry, region, returns)
    return program


@dataclass
class _Loop:
    opener: int
    body: int
    counter: int
    end: int
    exit: int
    kind: str
    parent: Optional[int]
    tested: bool = False
    test: int = 0


def _target(ins: Instruction, rel: int) -> int:
    return ins.next_pc + rel


def _verify(program: Program, registry: Registry, region: Region) -> None:
    starts = set(region.by_pc)
    jumps = []
    loops: List[_Loop] = []
    all_loops: List[_Loop] = []
    while_exits = []
    slots = set()
    halted = False
    for ins in region.instructions:
        op, a = ins.op, ins.args
        halted = False
        if op in ("CALL_FN", "CALL_METHOD"):
            imp = program.imports[a[0]]
            if (op == "CALL_FN") != (imp.kind == "function"):
                _fail(op + " at offset " + str(ins.pc) + " names import " + str(a[0]) + ", which is a " + ("method" if imp.kind == "method" else "function"))
            binding = registry.functions[imp.canonical] if imp.kind == "function" else registry.method_by_signature(imp.canonical)
            if len(binding.signature.params) != a[1]: _fail(op + " at offset " + str(ins.pc) + " passes " + str(a[1]) + " argument(s), the import takes " + str(len(binding.signature.params)))
        if op in ("JUMP", "JUMP_IF_FALSE", "JUMP_IF_TRUE"):
            rel = a[0]
            if rel < 0: _fail("jump at offset " + str(ins.pc) + " goes backwards outside a range loop")
            jumps.append((ins.pc, _target(ins, rel), True))
        elif op == "FOR_RANGE":
            counter, end, rel = a
            if counter >= len(region.locals): _fail("FOR_RANGE counter local index " + str(counter) + " out of range")
            if end >= len(region.locals): _fail("FOR_RANGE end local index " + str(end) + " out of range")
            if counter == end: _fail("FOR_RANGE counter and end slots must be distinct")
            for slot in (counter, end):
                local = region.locals[slot]
                if not local.hidden or local.type_name != "int": _fail("FOR_RANGE at offset " + str(ins.pc) + " requires hidden int local " + str(slot) + ", got " + ("" if local.hidden else "visible ") + local.type_name)
                if slot in slots: _fail("FOR_RANGE slot " + str(slot) + " is already owned by another range loop")
                slots.add(slot)
            exit_pc = _target(ins, rel)
            if exit_pc <= ins.pc: _fail("FOR_RANGE at offset " + str(ins.pc) + " exits backwards")
            loops.append(_Loop(ins.pc, ins.next_pc, counter, end, exit_pc, "range", loops[-1].opener if loops else None))
        elif op == "FOR_NEXT":
            end, rel = a
            if not loops or loops[-1].kind != "range": _fail("FOR_NEXT at offset " + str(ins.pc) + " has no matching FOR_RANGE")
            frame = loops.pop()
            if end != frame.end: _fail("FOR_NEXT at offset " + str(ins.pc) + " names end slot " + str(end) + ", expected " + str(frame.end))
            if _target(ins, rel) != frame.body: _fail("FOR_NEXT at offset " + str(ins.pc) + " must return to its FOR_RANGE body")
            if rel >= 0: _fail("FOR_NEXT at offset " + str(ins.pc) + " must jump backwards")
            jumps.append((ins.pc, frame.body, False))
            region.loop_pairs[ins.pc] = (frame.counter, frame.end)
            if frame.exit != ins.next_pc: _fail("FOR_RANGE at offset " + str(frame.opener) + " must exit immediately after its FOR_NEXT")
            all_loops.append(frame)
        elif op == "WHILE_BEGIN":
            loops.append(_Loop(ins.pc, ins.next_pc, 0, 0, 0, "while", loops[-1].opener if loops else None))
        elif op == "WHILE_TEST":
            if not loops or loops[-1].kind != "while": _fail("WHILE_TEST at offset " + str(ins.pc) + " has no matching WHILE_BEGIN")
            frame = loops[-1]
            if frame.tested: _fail("WHILE_BEGIN at offset " + str(frame.opener) + " has more than one WHILE_TEST")
            if a[0] < 0: _fail("WHILE_TEST at offset " + str(ins.pc) + " exits backwards")
            frame.tested = True; frame.test = ins.pc; frame.exit = _target(ins, a[0])
            while_exits.append((ins.pc, frame.exit))
        elif op == "LOOP_BACK":
            if not loops or loops[-1].kind != "while" or not loops[-1].tested: _fail("LOOP_BACK at offset " + str(ins.pc) + " has no matching tested WHILE_BEGIN")
            frame = loops.pop()
            if _target(ins, a[0]) != frame.opener: _fail("LOOP_BACK at offset " + str(ins.pc) + " does not target its paired WHILE_BEGIN")
            if frame.exit != ins.next_pc: _fail("WHILE_TEST at offset " + str(frame.opener) + " must exit immediately after its LOOP_BACK")
            all_loops.append(frame)
            jumps.append((ins.pc, frame.opener, False))
        elif op == "HALT":
            if loops: _fail("HALT inside loop")
            halted = True
    if not halted: _fail("code does not end with HALT")
    if loops:
        frame = loops[-1]
        _fail(("FOR_RANGE" if frame.kind == "range" else "WHILE_BEGIN") + " at offset " + str(frame.opener) + " is not closed")
    for at, target, ordinary in jumps:
        if target not in starts: _fail("jump at offset " + str(at) + " targets " + str(target) + ", not an instruction start")
        if ordinary:
            def owner(pc):
                found = None
                for frame in all_loops:
                    if frame.body <= pc < frame.exit: found = frame.opener
                return found
            from_loop, to_loop = owner(at), owner(target)
            frame = next((f for f in all_loops if f.opener == from_loop), None)
            if frame and frame.kind == "while" and at < frame.test < target: _fail("jump at offset " + str(at) + " skips its WHILE_TEST")
            if from_loop != to_loop:
                loop = next((f for f in all_loops if f.opener == from_loop), None)
                is_break = loop is not None and loop.exit == target and to_loop == loop.parent
                if not is_break: _fail("jump at offset " + str(at) + " crosses a loop boundary")
    for frame in all_loops:
        if frame.exit not in starts: _fail(("FOR_RANGE" if frame.kind == "range" else "WHILE_BEGIN") + " at offset " + str(frame.opener) + " exits to " + str(frame.exit) + ", not an instruction start")
    for at, target in while_exits:
        if target not in starts or not any(f.kind == "while" and f.opener < at and f.exit == target for f in all_loops):
            _fail("WHILE_TEST at offset " + str(at) + " exits to an invalid loop region")


def _verify_stack(program: Program, registry: Registry, region: Region, returns: Optional[str]) -> None:
    insns = region.instructions
    if not insns: _fail("code is empty")
    starts = {i.pc: n for n, i in enumerate(insns)}
    depths: Dict[int, int] = {insns[0].pc: 0}
    work = [insns[0].pc]
    has_loop = any(i.op in ("FOR_RANGE", "WHILE_BEGIN") for i in insns)
    if not has_loop and returns is None:
        return
    arity = {**{i:1 for i in range(0,5)}, **{i:2 for i in (5,6,7,15,16)}, **{i:3 for i in (8,9,17)}, **{i:1 for i in (10,11,12,13,14)}}
    while work:
        pc = work.pop()
        ins = region.by_pc[pc]
        op, a = ins.op, ins.args
        pop, push, targets, fall = 0, 0, [], True
        if op in ("PUSH_INT", "PUSH_FLOAT", "PUSH_STR", "PUSH_BOOL", "LOAD_LOCAL", "LOAD_CTX"): push = 1
        elif op in ("STORE_LOCAL", "POP"): pop = 1
        elif op == "CALL_FN":
            binding = registry.functions[program.imports[a[0]].canonical]
            pop = a[1]; push = 0 if binding.signature.returns == "void" else 1
        elif op == "CALL_METHOD":
            binding = registry.method_by_signature(program.imports[a[0]].canonical)
            pop = a[1] + 1; push = 0 if binding.signature.returns == "void" else 1
        elif op in ("EQ","NE","ADD_I","SUB_I","MUL_I","DIV_I","MOD_I","ADD_F","SUB_F","MUL_F","DIV_F","LT_I","LE_I","GT_I","GE_I","LT_F","LE_F","GT_F","GE_F","CONCAT"): pop,push=2,1
        elif op in ("NOT","NEG_I","NEG_F","I2F","I2S","F2S","B2S"): pop,push=1,1
        elif op == "MATH": pop,push=arity[a[0]],1
        elif op == "DUP": pop,push=1,2
        elif op == "JUMP": targets=[_target(ins,a[0])]; fall=False
        elif op in ("JUMP_IF_FALSE","JUMP_IF_TRUE"): pop=1; targets=[_target(ins,a[0])]
        elif op == "FOR_RANGE": pop=2; targets=[_target(ins,a[2])]
        elif op == "FOR_NEXT": targets=[_target(ins,a[1])]
        elif op == "WHILE_TEST": pop=1; targets=[_target(ins,a[0])]
        elif op == "LOOP_BACK": targets=[_target(ins,a[0])]; fall=False
        elif op == "HALT": fall=False
        depth = depths[pc]
        if depth < pop: _fail("operand stack underflow at offset " + str(pc))
        after = depth - pop + push
        if op == "HALT" and returns is not None and after != (0 if returns == "void" else 1):
            _fail("HALT leaves " + str(after) + " values, interface returns " + returns)
        nexts = list(targets)
        if fall:
            ix = starts[pc]
            if ix + 1 >= len(insns): _fail("control flow falls past the end of code")
            nexts.append(insns[ix + 1].pc)
        for target in nexts:
            if target not in starts: _fail("control flow targets " + str(target) + ", not an instruction start")
            old = depths.get(target)
            if old is None:
                depths[target] = after; work.append(target)
            elif old != after:
                _fail("inconsistent operand stack depth at control-flow join " + str(target) + ": " + str(old) + " versus " + str(after))
