"""Typed host registry. The VM binds canonical signatures before execution."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple
from .errors import LmcodeError

Callback = Callable[["Context", Any, List[Any]], Any]


@dataclass(frozen=True)
class Signature:
    params: Tuple[str, ...]
    returns: str

    def canonical(self, name: str, owner: Optional[str] = None) -> str:
        args = ", ".join(self.params)
        if owner is None:
            return "fn " + name + "(" + args + ") -> " + self.returns
        return "method " + owner + "." + name + "(" + args + ") -> " + self.returns


@dataclass(frozen=True)
class FunctionBinding:
    name: str
    signature: Signature
    callback: Callback
    dry_callback: Optional[Callback] = None
    dry_uses_real: bool = False
    is_std: bool = False
    raw_strings: bool = False
    allow_dry_null: bool = False


@dataclass(frozen=True)
class MethodBinding:
    owner: str
    name: str
    signature: Signature
    callback: Callback
    dry_callback: Optional[Callback] = None
    dry_uses_real: bool = False
    is_std: bool = False
    raw_strings: bool = False


@dataclass(frozen=True)
class ObjectRef:
    type_name: str
    value: Any
    identity: int = 0


@dataclass
class Context:
    values: Dict[str, Any]
    dry_mode: bool = False
    result_sink: Any = None
    invocation_index: int = 0

    def __init__(self, values: Optional[Dict[str, Any]] = None, dry_mode: bool = False) -> None:
        self.values = dict(values or {})
        self.dry_mode = bool(dry_mode)
        self.result_sink = None
        self.invocation_index = 0

    def set(self, name: str, value: Any) -> None:
        self.values[name] = value

    def dry(self) -> bool:
        return self.dry_mode

    def set_dry(self, value: bool) -> None:
        self.dry_mode = bool(value)


def dry(callback: Any) -> Any:
    """Mark a callback as the dry-mode implementation; pass real for explicit opt-in."""
    return DrySlot(callback)


class _Real:
    pass


real = _Real()


@dataclass(frozen=True)
class DrySlot:
    callback: Any


class Registry:
    def __init__(self, include_std: bool = True) -> None:
        self.functions: Dict[str, FunctionBinding] = {}
        self.methods: Dict[str, MethodBinding] = {}
        self.contexts: Dict[str, str] = {}
        self.enum_types = set()
        self.std_signatures = set()
        self.std_enabled = False
        self._run_active = False
        self._run_generation = 0
        self.result_sink = None
        if include_std:
            from .stdlib import register_std
            register_std(self)

    def enum(self, name: str) -> "Registry":
        self.enum_types.add(name)
        return self

    def context(self, name: str, type_name: str) -> "Registry":
        old = self.contexts.get(name)
        if old is not None and old != type_name:
            raise LmcodeError("LOAD_UNBOUND", "context variable '" + name + "' has conflicting types")
        self.contexts[name] = type_name
        return self

    def function(self, name: str, params: List[str], returns: str, callback: Callback,
                 dry_callback: Any = None, _std: bool = False, _raw: bool = False, _allow_dry_null: bool = False) -> "Registry":
        signature = Signature(tuple(params), returns)
        key = signature.canonical(name)
        if key in self.functions:
            raise LmcodeError("LOAD_UNBOUND", "duplicate host function " + key)
        slot = dry_callback if isinstance(dry_callback, DrySlot) else None
        self.functions[key] = FunctionBinding(name, signature, callback,
            slot.callback if slot is not None and slot.callback is not real else None,
            slot is not None and slot.callback is real, _std, _raw, _allow_dry_null)
        if _std:
            self.std_signatures.add(key)
        return self

    def method(self, owner: str, name: str, params: List[str], returns: str, callback: Callback,
               dry_callback: Any = None, _std: bool = False, _raw: bool = False) -> "Registry":
        signature = Signature(tuple(params), returns)
        key = signature.canonical(name, owner)
        if key in self.methods:
            raise LmcodeError("LOAD_UNBOUND", "duplicate host method " + key)
        slot = dry_callback if isinstance(dry_callback, DrySlot) else None
        self.methods[key] = MethodBinding(owner, name, signature, callback,
            slot.callback if slot is not None and slot.callback is not real else None,
            slot is not None and slot.callback is real, _std, _raw)
        if _std:
            self.std_signatures.add(key)
        return self

    def set_result_sink(self, sink: Any) -> "Registry":
        self.result_sink = sink
        return self

    def begin_run(self) -> int:
        if self.std_enabled and self._run_active:
            raise LmcodeError("RUN_HOST", "standard runtime does not support nested or overlapping runs")
        self._run_generation += 1
        self._run_active = True
        return self._run_generation

    def end_run(self, generation: int) -> None:
        if generation == self._run_generation:
            self._run_active = False

    def method_by_signature(self, canonical: str):
        exact = self.methods.get(canonical)
        if exact is not None:
            return exact
        head = canonical.split("(", 1)[0]
        if not head.startswith("method ") or "." not in head:
            return None
        owner = head[len("method "):].split(".", 1)[0]
        if canonical.endswith(" -> " + owner):
            alternate = canonical[:-len(owner)] + "self"
        elif canonical.endswith(" -> self"):
            alternate = canonical[:-len("self")] + owner
        else:
            return None
        return self.methods.get(alternate)

    def signatures(self) -> List[str]:
        result = list(self.functions)
        result.extend(self.methods)
        return sorted(result)

    def declared_for(self, canonical: str) -> List[str]:
        return [s for s in self.signatures() if s.split("(", 1)[0] == canonical.split("(", 1)[0]]
