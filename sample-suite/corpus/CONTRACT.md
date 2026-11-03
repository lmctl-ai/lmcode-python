# Shop host contract (shared by every sample)

Schema bytes: `sample.dsl.json` (schema 2, merged default std); domain-only declarations: `host.schema.json`.
- Fresh process per case. `shop` and `ledger` are contexts. Own object pointers in a stable per-process arena.
- Money is signed int64 cents. `money(int)` / `shop.price(int)` accept cents;
  their float overloads accept units and round half away from zero to cents (finite/in-range only).
  All integer money operations wrap modulo 2^64. `Money.set(int)` mutates/returns its receiver.
- `Money.currency()` and `Shop.currency()` return string-backed enum `Currency.USD`.
- Shop label = `sample shop`; items contain Money cents [125,250,375]; total = Money(750).
- `Items.at` outside [0,len) throws `items: index out of range`.
- `Ledger.record(Money)` wraps balance and increments entries; returns the same Ledger.
  `note(string)` stores text (void), `note()` retrieves it; initial note empty, balance/entries zero.
  `reject(string)` throws that exact message. `fee(int)` adds 5 with int64 wrapping.
- `sample_tmp()` returns SAMPLE_TMP unchanged, or throws `SAMPLE_TMP is required`.
- Register default std and optional `print(string)` / `assert_close(float,float,float)` testing catalog.
- The schema's `interfaces` map declares two SAM interfaces: `Adjuster` (`(Money) -> void`) and `Score`
  (`(Money) -> int`). A rule method is a top-level `fn` with a leading `@NAME` annotation and a trailing
  `implements NAME` clause; its signature must match the interface exactly. An annotated rule compiles to a
  lmcode bytecode (DSLB v6) rule entry (own code/locals/line table, shared pools); a plain call from the chunk body still
  invokes an inlined copy. An annotation without `implements` is a compile error (exit 2).
- After the body runs, the host enumerates the program's rule entries in source order: every entry
  annotated `@item` is called once per shop item, in order, with the item's Money handle; every entry
  annotated `@total` is called once with the `Shop.total()` Money handle; entries with other annotations
  are never called. A non-void entry result is printed as `entry NAME = VALUE` in call order (VALUE uses
  the same text as `str()`). Entry-call failures are run-phase errors. The result object gains
  `"entries_called": N`, the number of entry calls the host made (0 for programs without rules).
- One invocation accepts repeated `--lmcode FILE` pairs. `--first FILE` and
  `--last FILE` are role fragments: first roles dispatch before normal roles, last
  roles afterward, stable within each role. The private invocation descriptor maps
  unchanged file strings to add indices; standalone pairs use occurrence order.
- One Host/context/ledger spans the invocation. Each slot owns its own result sink,
  spanning body and selected entries; complete validates/seals before another slot.
  Results are emitted in add order regardless of dispatch order. Same program twice
  means two independent slots sharing host effects. No implicit merge/deduplication.
- Preserve traces/entry diagnostics. Successful global application validation emits
  one tagged `{"host_summary":{"balance": N, "entries": N, "note": TEXT,
  "entries_called": N}}` diagnostic. It is not the program result.
- One terminal compact invocation envelope frame, including controlled failures:
  `LMCODE_RETURN_BEGIN\n<ENVELOPE>\nLMCODE_RETURN_END\n` (final LF, flush once).
  Single success is `{"ok":true,"result":VALUE}`; builder success has an add-order
  result array and required `parts`, including one-slot builders. Unset is null.
  No per-part frames or duplicate unframed success records.
- Failures use compact ordered ok/phase/code/message/line/column/part fields. No
  payload/parts on failure. First failure wins; known builder slot has part including
  zero; single/global omits it. A negative final shared ledger is global APP_FAIL,
  `ledger: negative balance`, exit4. CLI/load/run/app exit2/3/3/4 respectively.
- Canonical load messages remain LOAD_BAD_BYTECODE -> `invalid sample bytecode`,
  LOAD_SCHEMA_MISMATCH -> `sample schema mismatch`, LOAD_UNBOUND -> `sample import
  mismatch`; run errors retain the located SDK diagnostic. Other IO setup failures
  become APP_FAIL `cannot read sample input`, without machine paths.
- Discovery flags retain exact schema/signature/version bytes and ignore execution
  metadata. Usage/unknown options produce CLI_USAGE failure frames before file IO.

## Native conversion probes (shared by all ports)

- `host_int`, `host_float`, `host_bool`, `host_bytes` return the argument unchanged;
  use int64/binary64/bool/raw bytes, never host `int32` or a lossy UTF-8 decode.
- `host_float_case(string)` accepts `-0`, `nan` (quiet NaN), `inf`, `-inf`, `large`
  (1e21), `subnormal` (smallest positive binary64). `str(NaN)` is canonical `nan`
  independent of sign/payload; other numbers use 15-significant-digit general format.
- `host_hex(string)` returns lowercase hexadecimal for every byte, including NUL
  and invalid UTF-8. Runner fixtures are defined as hex in manifest.json, not written
  using the file API under test. Never print undecodable bytes into the JSON result.
- `host_echo_money` returns the identical handle; `host_same` tests identity, not
  equal cents. `host_null` returns a typed null Money; `host_is_null` observes it.
  A Money method on null throws `RUN_HOST`, `money: null handle`. `host_void`
  returns no VM value. `host_wrong` deliberately returns an Items-tagged value
  despite declaring Money: using it as a Money receiver raises `RUN_ERROR`.
- Wrong **registered import** handle types are a distinct `LOAD_UNBOUND` failure;
  a loader cannot know a callback's future dynamic return value. Mutation 092 tests it.
- `host_str_list`, `host_int_list`, `host_float_list`, `host_str_map` COPY the input
  to a new registry-arena object and append `host`, `9`, `0.5`, or `host=yes`.
  Inputs stay unchanged; map order is preserved. Standard handles expire after run().
- `host_sum` accepts exactly 255 int arguments and sums with int64 wrapping.
  `host_long_` followed by 128 `x` characters is an int identity function.
- There is no recursive bytecode call stack: recursive inline functions are rejected
  with compiler exit 2 (`compile-errors/`). The 32-level acyclic inline case and
  nested 255-argument call exercise compiler nesting and a 509-slot VM operand stack.
- Million-iteration case 058 has a five-second harness limit (C++ measured 0.068 s
  locally); report timeouts as failures. The VM itself still has no execution cap.
