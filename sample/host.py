"""Shop/Ledger host used by the canonical sample bytecode suite."""
from __future__ import annotations
from dataclasses import dataclass
import math
import os
from lmcode import HostError, Registry, dry
from lmcode.registry import ObjectRef
from lmcode.vm import _format_g15
from lmcode.stdlib import register_testing


def wrap64(value):
    value &= (1 << 64) - 1
    return value - (1 << 64) if value & (1 << 63) else value


@dataclass
class Money:
    cents: int


@dataclass
class Items:
    values: list


@dataclass
class Shop:
    items: Items


@dataclass
class Ledger:
    balance: int = 0
    entries: int = 0
    note_text: str = ""


class Host:
    def __init__(self, dry_mode=False, output=None):
        self.registry = Registry()
        self.registry.enum("Currency")
        self.shop = Shop(Items([]))
        self.ledger = Ledger()
        self.dry_mode = dry_mode
        if not dry_mode:
            self.shop.items.values.extend([Money(125), Money(250), Money(375)])
        register_testing(self.registry, output)
        self._register_conversions()
        self._register_shop()

    def _money(self, cents):
        return Money(wrap64(cents))

    @staticmethod
    def _money_value(value):
        if value is None:
            raise HostError("money: null handle")
        if isinstance(value, ObjectRef):
            value = value.value
        if not isinstance(value, Money):
            raise HostError("money: null handle")
        return value

    def _units(self, units):
        scaled = units * 100
        if not math.isfinite(scaled):
            raise HostError("money: amount out of range")
        cents = math.ceil(scaled - 0.5) if scaled < 0 else math.floor(scaled + 0.5)
        if cents < -(1 << 63) or cents >= (1 << 63):
            raise HostError("money: amount out of range")
        return self._money(int(cents))

    def _register_conversions(self):
        r = self.registry
        r.function("host_int", ["int"], "int", lambda _c, _s, a: a[0])
        r.function("host_float", ["float"], "float", lambda _c, _s, a: a[0])
        r.function("host_bool", ["bool"], "bool", lambda _c, _s, a: a[0])
        r.function("host_bytes", ["string"], "string", lambda _c, _s, a: a[0], _raw=True)
        r.function("host_hex", ["string"], "string", lambda _c, _s, a: a[0].encode("latin-1").hex(), _raw=True)
        cases = {"-0": -0.0, "nan": math.nan, "inf": math.inf, "-inf": -math.inf,
                 "large": 1e21, "subnormal": float.fromhex("0x0.0000000000001p-1022")}
        def float_case(_c, _s, args):
            if args[0] not in cases:
                raise HostError("host_float_case: unknown case")
            return cases[args[0]]
        r.function("host_float_case", ["string"], "float", float_case)
        r.function("host_echo_money", ["Money"], "Money", lambda _c, _s, a: a[0])
        r.function("host_same", ["Money", "Money"], "bool", lambda _c, _s, a: a[0] is a[1])
        r.function("host_null", [], "Money", lambda _c, _s, _a: ObjectRef("Money", None, id(None)))
        r.function("host_is_null", ["Money"], "bool", lambda _c, _s, a: a[0] is None)
        r.function("host_wrong", [], "Money", lambda _c, _s, _a: ObjectRef("Items", None, id(None)))
        r.function("host_void", [], "void", lambda _c, _s, _a: None)
        for signature, typ, appended in (("host_str_list", "StrList", "host"),
                                         ("host_int_list", "IntList", 9),
                                         ("host_float_list", "FloatList", 0.5)):
            def copy_list(_c, _s, args, type_name=typ, extra=appended):
                source = args[0]
                data = type(source)(type_name, list(source.value) + [extra])
                return ObjectRef(type_name, data, id(data))
            r.function(signature, [typ], typ, copy_list)
        def copy_map(_c, _s, args):
            source = args[0]
            data = type(source)("StrMap", dict(source.value))
            data.value["host"] = "yes"
            return ObjectRef("StrMap", data, id(data))
        r.function("host_str_map", ["StrMap"], "StrMap", copy_map)
        r.function("host_sum", ["int"] * 255, "int", lambda _c, _s, a: wrap64(sum(a)))
        r.function("host_long_" + "x" * 128, ["int"], "int", lambda _c, _s, a: a[0])

    def _register_shop(self):
        r = self.registry
        r.context("shop", "Shop").context("ledger", "Ledger")
        r.function("money", ["int"], "Money", lambda _c, _s, a: self._money(a[0]))
        r.function("money", ["float"], "Money", lambda _c, _s, a: self._units(a[0]))
        r.function("fee", ["int"], "int", lambda _c, _s, a: wrap64(a[0] + 5))
        def sample_tmp():
            value = os.environ.get("SAMPLE_TMP")
            if not value:
                raise HostError("SAMPLE_TMP is required")
            return value
        r.function("sample_tmp", [], "string", lambda _c, _s, _a: sample_tmp(), dry(dry_sample_tmp))
        self._register_money_methods(r)
        r.method("Shop", "items", [], "Items", lambda _c, shop, _a: shop.items)
        r.method("Shop", "total", [], "Money", lambda _c, shop, _a: self._money(sum(item.cents for item in shop.items.values)))
        r.method("Shop", "price", ["int"], "Money", lambda _c, _shop, a: self._money(a[0]))
        r.method("Shop", "price", ["float"], "Money", lambda _c, _shop, a: self._units(a[0]))
        r.method("Shop", "currency", [], "Currency", lambda _c, _shop, _a: "USD")
        r.method("Shop", "label", [], "string", lambda _c, _shop, _a: "sample shop")
        r.method("Items", "len", [], "int", lambda _c, items, _a: len(items.values))
        def item_at(_c, items, args):
            index = args[0]
            if index < 0 or index >= len(items.values):
                raise HostError("items: index out of range")
            return items.values[index]
        r.method("Items", "at", ["int"], "Money", item_at)
        r.method("Ledger", "record", ["Money"], "self", lambda _c, ledger, a: self._record(ledger, a[0]))
        r.method("Ledger", "balance", [], "Money", lambda _c, ledger, _a: self._money(ledger.balance))
        r.method("Ledger", "count", [], "int", lambda _c, ledger, _a: ledger.entries)
        r.method("Ledger", "note", ["string"], "void", lambda _c, ledger, a: setattr(ledger, "note_text", a[0]))
        r.method("Ledger", "note", [], "string", lambda _c, ledger, _a: ledger.note_text)
        r.method("Ledger", "reject", ["string"], "void", lambda _c, _ledger, a: (_ for _ in ()).throw(HostError(a[0])))

    def _register_money_methods(self, registry):
        get = lambda money: self._money_value(money)
        registry.method("Money", "amount", [], "int", lambda _c, money, _a: get(money).cents)
        registry.method("Money", "currency", [], "Currency", lambda _c, money, _a: (get(money), "USD")[1])
        registry.method("Money", "plus", ["Money"], "Money", lambda _c, money, a: self._money(wrap64(get(money).cents + get(a[0]).cents)))
        registry.method("Money", "minus", ["Money"], "Money", lambda _c, money, a: self._money(wrap64(get(money).cents - get(a[0]).cents)))
        registry.method("Money", "times", ["int"], "Money", lambda _c, money, a: self._money(wrap64(get(money).cents * a[0])))
        registry.method("Money", "neg", [], "Money", lambda _c, money, _a: self._money(wrap64(-get(money).cents)))
        registry.method("Money", "set", ["int"], "self", lambda _c, money, a: self._set_money(money, a[0]))

    def _set_money(self, money, cents):
        money.cents = cents
        return money

    def _record(self, ledger, money):
        ledger.balance = wrap64(ledger.balance + self._money_value(money).cents)
        ledger.entries = wrap64(ledger.entries + 1)
        return ledger

    def summary(self, entries_called):
        import json
        note = json.dumps(self.ledger.note_text, ensure_ascii=False, separators=(",", ":"))
        return '{"host_summary":{"balance": ' + str(self.ledger.balance) + ', "entries": ' + str(self.ledger.entries) + ', "note": ' + note + ', "entries_called": ' + str(entries_called) + '}}\n'


def dry_sample_tmp(_context, _receiver, _args):
    value = os.environ.get("SAMPLE_TMP")
    if not value:
        raise HostError("SAMPLE_TMP is required")
    return value


def entry_text(value):
    if value is None:
        return "None"
    if isinstance(value, Money):
        return "Money(cents=" + str(value.cents) + ")"
    if type(value) is float:
        return _format_g15(value)
    return str(value)
