# Canonical Shop integration corpus

This is the source of truth for all eight `lmcode-*-sample` hosts.
See [CONTRACT.md](CONTRACT.md) for object semantics and the exact result protocol.
The full schema is [`sample.dsl.json`](sample.dsl.json); [host.schema.json](host.schema.json)
contains only the small shop/ledger domain. Every process starts with fresh state.

```sh
# Use a private mono main build at 0bc80277 or later.
export LMSCRIPT_BIN=/absolute/path/to/mono/lmscript/bin/lmscript
lmctl sample-suite/run-suite.lms /path/to/lmcode-cpp-sample
./sample-suite/run-suite.sh /path/to/lmcode-cpp-sample
./sample-suite/run-suite.sh dotnet /path/to/sample.dll
python3 sample-suite/compile.py
lmctl sample-suite/audit.lms
lmctl sample-suite/test-runner.lms
```

`run-suite.sh` checks the discovery/usage protocol, then executes each pinned
`.dslb` in a separate process with a fresh directory in `SAMPLE_TMP`. It compares
stdout bytes (including the unchanged shop diagnostic and the terminal return frame) and exit code; stderr must be empty.
No timestamps, absolute paths, OS error text, or libm decimal approximations are
part of expected output. `assert_close` checks approximate math without unstable
traces. Call arguments are an argv array, not a shell string. Each case has a
30-second harness timeout; the SDK VM itself has no execution limit.

`compile-errors/` contains 23 independently expected compiler rejections. The
checker asserts exit 2, diagnostic text, and that no bytecode is written; the
newer syntax/type cases also pin the reported source line and column. This is a
negative control suite, separate from runtime bytecode cases.

## Change the language or add a standard function

1. Change `programs/NNN-name.lms` (maximum 40 lines), and update `coverage.json`.
2. Merge `host.schema.json` with the current canonical standard:
   `python3 scripts/merge-std.py sample-suite/host.schema.json sample-suite/sample.dsl.json`.
3. Rebuild the C++ sample **against this schema and SDK**, then run `compile.py`.
4. Run `record.py /path/to/lmcode-cpp-sample` explicitly; review its expected-output diff.
   The manifest independently declares expected exits and return payloads: recording cannot
   bless an unexpected crash/error or a missing/reset result as success. `record.py` validates
   the terminal protocol and those independent values before writing expectations. Normal tests never regenerate expectations.
5. Run the corpus on at least one other SDK before accepting the oracle.
   Initial validation: C++ and Go matched all 77 cases exactly.
6. Commit sources, bytecode, manifest and expectations together. Sync the pinned
   suite into every sample and run every port's CI. `audit.py` parses actual
   bytecode import tables and fails if any canonical std signature is uncovered.

`compile.py --output TEMP_DIR` recompiles without changing the committed manifest,
for reproducibility checks. `LMSCRIPT_BIN` selects the compiler;
bytecode format is v6 (rule entries section). `protocol.py` independently derives signatures from the
schema, so a host missing/adding registrations fails even if no program calls it.
The malformed-bytecode and schema-hash cases are deterministic mutations of the
first compiler-emitted program, never hand-authored executable bytecode.

## Feature -> program matrix

| Program | Feature / called APIs |
|---|---|
| [001-literals](programs/001-literals.lms) | literals; print(string) |
| [002-arithmetic](programs/002-arithmetic.lms) | arithmetic; int operators; fee(int) |
| [003-boolean](programs/003-boolean.lms) | boolean; comparisons |
| [004-if-else](programs/004-if-else.lms) | if; else |
| [005-while](programs/005-while.lms) | while |
| [006-range-for](programs/006-range-for.lms) | range; for |
| [007-switch](programs/007-switch.lms) | switch; break; default |
| [008-function](programs/008-function.lms) | function; return |
| [009-money-overloads](programs/009-money-overloads.lms) | money(int); money(float); Shop.price(int); Shop.price(float) |
| [010-money-methods](programs/010-money-methods.lms) | Money.amount(); Money.currency(); Money.set(int) |
| [011-money-operators](programs/011-money-operators.lms) | Money.plus(Money); Money.minus(Money); Money.times(int); Money.neg(); Money r* |
| [012-shop-methods](programs/012-shop-methods.lms) | Shop.items(); Shop.total(); Shop.currency(); Shop.label() |
| [013-items-methods](programs/013-items-methods.lms) | Items.len(); Items.at(int) |
| [014-ledger-methods](programs/014-ledger-methods.lms) | Ledger.record(Money); Ledger.balance(); Ledger.note(string); Ledger.note(); Ledger.count() |
| [015-float-list](programs/015-float-list.lms) | float_list(); FloatList.add(float); FloatList.at(int); FloatList.clear(); FloatList.contains(float); FloatList.index_of(float); FloatList.len(); FloatList.set(int,float) |
| [016-int-list](programs/016-int-list.lms) | int_list(); IntList.add(int); IntList.at(int); IntList.clear(); IntList.contains(int); IntList.index_of(int); IntList.len(); IntList.set(int,int) |
| [017-str-list](programs/017-str-list.lms) | str_list(); StrList.add(string); StrList.at(int); StrList.clear(); StrList.contains(string); StrList.index_of(string); StrList.join(string); StrList.len(); StrList.set(int,string) |
| [018-str-map](programs/018-str-map.lms) | str_map(); StrMap.clear(); StrMap.get(string); StrMap.get_or(string,string); StrMap.has(string); StrMap.key_at(int); StrMap.len(); StrMap.remove(string); StrMap.set(string,string) |
| [019-math-int](programs/019-math-int.lms) | math_abs(int); math_ceil(int); math_floor(int); math_max(int,int); math_min(int,int); math_pow(int,int); math_round(int); math_sqrt(int) |
| [020-math-float](programs/020-math-float.lms) | math_abs(float); math_ceil(float); math_floor(float); math_max(float,float); math_min(float,float); math_pow(float,float); math_round(float); math_sqrt(float) |
| [021-string-predicates](programs/021-string-predicates.lms) | str_contains(string,string); str_ends_with(string,string); str_find(string,string); str_is_float(string); str_is_int(string); str_match(string,string); str_starts_with(string,string) |
| [022-string-transform](programs/022-string-transform.lms) | str_len(string); str_lower(string); str_repeat(string,int); str_replace(string,string,string); str_substr(string,int,int); str_trim(string); str_upper(string) |
| [023-string-convert](programs/023-string-convert.lms) | str_to_float(string); str_to_int(string); str_split(string,string) |
| [024-file-functions](programs/024-file-functions.lms) | sample_tmp(); file_write(string,string); file_append(string,string); file_exists(string); file_read(string); file_lines(string) |
| [025-assert-close](programs/025-assert-close.lms) | assert_close(float,float,float) |
| [026-divzero-expected-fail](programs/026-divzero-expected-fail.lms) | runtime divzero |
| [027-modzero-expected-fail](programs/027-modzero-expected-fail.lms) | runtime modzero |
| [028-assert-fail-expected-fail](programs/028-assert-fail-expected-fail.lms) | assert_close failure |
| [029-reject-expected-fail](programs/029-reject-expected-fail.lms) | Ledger.reject(string) |
| [030-negative-balance-expected-fail](programs/030-negative-balance-expected-fail.lms) | application negative balance |
| [031-items-oob-expected-fail](programs/031-items-oob-expected-fail.lms) | Items.at out of bounds |
| [032-intlist-oob-expected-fail](programs/032-intlist-oob-expected-fail.lms) | IntList.at out of bounds |
| [033-map-missing-expected-fail](programs/033-map-missing-expected-fail.lms) | StrMap missing key |
| [034-money-conversion](programs/034-money-conversion.lms) | int to Money conversion |
| [035-context-trace](programs/035-context-trace.lms) | context shop; context ledger |
| [036-nested-control](programs/036-nested-control.lms) | nested control flow |
| [037-map-iteration](programs/037-map-iteration.lms) | collection iteration |
| [038-floatlist-chain](programs/038-floatlist-chain.lms) | method chaining; bool expression |
| [039-enum-currency](programs/039-enum-currency.lms) | Currency enum |
| [040-full-trace](programs/040-full-trace.lms) | full integration trace |
| [041-int64-wrap](programs/041-int64-wrap.lms) | int64 wraparound |
| [042-short-circuit](programs/042-short-circuit.lms) | short circuit; runtime safety |
| [043-break-continue](programs/043-break-continue.lms) | break; continue |
| [044-items-foreach](programs/044-items-foreach.lms) | Items foreach |
| [045-switch-string-enum](programs/045-switch-string-enum.lms) | string switch; enum switch |
| [046-inner-heredoc](programs/046-inner-heredoc.lms) | inner raw heredoc <<TAG; inner dedent heredoc <<~TAG; raw ${} opacity |
| [047-outer-splice](programs/047-outer-splice.lms) | outer int/float/string/bool splices |
| [048-math-derived](programs/048-math-derived.lms) | all 18 MATH opcodes; int/float widening |
| [049-int-boundary](programs/049-int-boundary.lms) | int64 native roundtrip |
| [050-float-boundary](programs/050-float-boundary.lms) | binary64 special values and formatting |
| [051-bool-boundary](programs/051-bool-boundary.lms) | native bool roundtrip |
| [052-byte-boundary](programs/052-byte-boundary.lms) | empty NUL multibyte byte-string roundtrip |
| [053-file-invalid-utf8](programs/053-file-invalid-utf8.lms) | invalid UTF8 file bytes cross callback |
| [054-megabyte-string](programs/054-megabyte-string.lms) | one MiB byte-string boundary |
| [055-object-handles](programs/055-object-handles.lms) | object lifetime identity null void |
| [056-collection-boundary](programs/056-collection-boundary.lms) | all standard collection types cross native boundary both ways |
| [057-nested-inline-error](programs/057-nested-inline-error.lms) | located error inside nested inline functions |
| [058-million-loop](programs/058-million-loop.lms) | million iterations performance sanity |
| [059-deep-inline](programs/059-deep-inline.lms) | deep acyclic inlining no runtime call stack |
| [060-many-arguments](programs/060-many-arguments.lms) | 255 native arguments; 509 slot VM operand stack |
| [061-long-identifier](programs/061-long-identifier.lms) | long native import identifier |
| [062-null-receiver](programs/062-null-receiver.lms) | null handle method error is located |
| [063-wrong-runtime-handle](programs/063-wrong-runtime-handle.lms) | dynamic wrong handle type runtime failure |
| [067-rule-methods](programs/067-rule-methods.lms) | @NAME rule annotation; implements Adjuster SAM interface |
| [068-rule-entries](programs/068-rule-entries.lms) | rule entry table; @item/@total dispatch; @never never called; entries_called |
| [069-rule-value-entry](programs/069-rule-value-entry.lms) | value rule entry; implements Score SAM interface; entry result printed |
| [093-v5-refused](bytecode/093-v5-refused.dslb) | loader refuses a v5 file |
| [090-bad-bytecode](bytecode/090-bad-bytecode.dslb) | loader bad-bytecode |
| [091-schema-mismatch](bytecode/091-schema-mismatch.dslb) | loader schema-mismatch |
| [092-wrong-handle-import](bytecode/092-wrong-handle-import.dslb) | declared wrong handle type load error |

## CI entry points

SDK pushes/PRs run `.github/workflows/sample-suite.yml` against a pinned reference
host source, the **current** SDK/header and this canonical corpus. That makes a
new standard signature without a corpus import a CI failure. The reference
sample also runs its vendored snapshot natively on Linux/macOS/Windows.
After a compiler/language change, its release pipeline can send the
`lmcode-language-changed` repository_dispatch event with `compiler` in the payload;
or the language owner runs:

```sh
gh workflow run sample-suite.yml -R lmctl-ai/lmcode-cpp -f compiler=latest
```

The job recompiles sources and rejects bytecode drift for explicit review; it
never silently regenerates oracle files. Each additional sample should run the
same `run-suite.sh` in its own CI and sync the reviewed suite lock on updates.

## Conversion and all-port matrix

Programs 049–063 add exact native conversion probes; `CONTRACT.md` defines their
host behavior. The one-MiB/NUL/invalid-UTF8 fixtures are bytes, never lossy strings.
The million-iteration case has a five-second limit; the 255-argument nested call
has a 509-slot operand stack. Recursive inline functions are deliberately rejected
by `check-compile-errors.py` (exit 2), not treated as a supported recursive VM feature.

```sh
./sample-suite/run-all-samples.sh --all
./sample-suite/run-all-samples.sh --all --env-file /path/to/sample-paths.json
```

Defaults are `~/repos/dsl/lmcode-{c,cpp,rust,go,csharp,java,kotlin,scala}-sample`.
Native defaults use Cargo for Rust, `dotnet build` for C#, Maven for Kotlin,
and sbt for Scala (including its generated runtime classpath). C/C++ use
`make all`, Go uses `go build`, and Java uses its `build.sh`. Build commands have
a 600-second timeout (`SAMPLE_TIMEOUT` overrides it).
Managed-language launchers should `exec` their runtime. JSON/env files may set
`SAMPLE_CPP_DIR` (and other language names), `SAMPLE_LANG_BUILD` and
`SAMPLE_LANG_COMMAND` (JSON argv arrays), `SAMPLE_CORPUS`, or `SAMPLE_STATE`.
Commands run from their sample checkout. Missing builds/ports are FAIL, not SKIP.
The runner validates the canonical corpus and compiler rejection, builds every
port, checks its CLI, and runs every case against expected bytes AND against the
other actual byte outputs. It prints a program x sample matrix and preserves
hex-encoded observations and timings in `~/.local/state/lmctl/sample-matrix/`.
Weekly/manual/path-triggered `.github/workflows/samples.yml` checks all eight public
repos on Linux; during rollout it intentionally fails until every port is implemented.


## Catalog v2 data examples

Programs 101-105 exercise all 99 new container/Json imports; 106-108 pin their runtime traps. Expectations are recorded only from the rebuilt C++ reference. The all-samples matrix reports known released-v1 SDK pins (or exact legacy-only registry surfaces for unpinned Go builds) as pending FAIL; every available port still builds and runs, and pending ports
never count as passes. Single-host protocol/run-suite checks never skip.

## Compiler literal cases

Cases 201–205 cover contextual word/numeric lists, int64 boundaries, all typed map
literals, single evaluation order, raw JSONC documents and legacy bindings. They
are supported by the published compiler (`@lmctl-ai/lmctl` 0.2.442 and later);
set `LMSCRIPT_BIN` to a development lmscript build only when testing unreleased
compiler work.
Their manifest entries declare `compiler_features: ["lmcode-literals-v1"]`;
source reproduction must report an unsupported compiler explicitly. `compile.py --output DIR --exclude-feature lmcode-literals-v1` requires a source build that exports its compiler library; the public npm package does not provide that private module. It is not part of CI.

## Compiler rule-method cases

Case 067 and compile-errors/rule-method-mismatch cover R47/R48 rule methods: an
`@NAME` annotation directly before a top-level `fn`, plus an `implements Adjuster`
clause bound to the schema's SAM interface (`(Money) -> void`). The manifest entry declares
`compiler_features: ["lmcode-rule-methods-v1"]`; rule methods compile with the
published `@lmctl-ai/lmctl` 0.2.442 or later. Source reproduction with an older
compiler is an explicit error, as for any unsupported compiler.

Cases 068/069, compile-errors/rule-annotation-without-implements and mutation
093-v5-refused cover R49 rule entries (lmcode bytecode (DSLB v6)): every annotated rule compiles to
a self-contained entry; after the body runs the host calls each `@item` entry once
per shop item in order and each `@total` entry once with `shop.total()`, never
calls other annotations, prints non-void results as `entry NAME = VALUE`, and
reports the count as `"entries_called"` in the result object. The whole corpus is
DSLB v6 (version 6 is the only bytecode any current runtime accepts), first
published as `@lmctl-ai/lmctl` 0.2.444, which reproduces every pinned `.dslb`
byte-for-byte; 0.2.442/0.2.443 accept the rule syntax but still write v5. The
manifest entries declare `compiler_features: ["lmcode-rule-entries-v1"]`. `compile.py --output DIR --exclude-feature lmcode-rule-methods-v1` or
`--exclude-feature lmcode-rule-entries-v1` remains a source-build-only partial
reproduction check and never rewrites the canonical manifest.

`run-all-samples.sh --ports cpp,c,rust,go,csharp` selects an explicit subset when
other owners' repositories must not be accessed. Excluded ports are listed in
the report and are never counted as passes; `--all` retains the full matrix.

`check-recompile.lms` type-checks the source fixtures with the public compiler and verifies four bytecode mutation controls. The checked-in bytecode hashes and runtime suite remain the bytecode oracle; the public npm package does not expose a bytecode export API.
A verified 72-signature v1 compiler reports literal-feature cases as SKIP while
reproducing all compatible cases. A v2 or otherwise unknown compiler failure is
an error; `LMCODE_REQUIRE_LITERAL_COMPILER=1` also makes v1 gaps fatal. Runtime
execution always covers the entire corpus, regardless of compiler capabilities.

Std v3 adds programs 301–305: strict byte codecs, all six map snapshots, independent mutation and exact decoder errors. The corpus has 123 cases, including text-template success/error coverage, and runs across C++, C, Go, Java, Kotlin, Scala, Rust and C#.

Reviewer cases 311–313 extend v3 coverage with binary padding boundaries, bidirectional snapshot mutation and the exact noncanonical Base64 trap.

## lmscript test drivers

`run-suite.lms`, `audit.lms`, `check-recompile.lms`, and `test-runner.lms`
own test orchestration and assertions. Run them with either `lmctl FILE.lms`
or `lmscript FILE.lms` from the repository root. Set `LMCODE_SUITE` to an
absolute corpus directory when using another working directory. Normal execution
checks statically, then runs once. Use a private mono main build at 0bc80277 or
later and set `LMSCRIPT_BIN=/absolute/path/to/mono/lmscript/bin/lmscript`.
`lmctl` also runs URLs ending in `.lms`,
but these tests need their checkout and local native executables.

`bytes.mjs` supplies binary hashing, import decoding, binary mutation and
exact subprocess capture through Node (already required by lmscript). The
`.lms` drivers select tests and check outcomes. Each host invocation gets
fresh fixtures and a timeout; the adapter removes its temporary files even
on failure. Python corpus authoring tools and the separate cross-port matrix
remain available; sample release CI no longer uses Python test drivers.

## Invocation return cases (slice 6)

The `360-*` through `368-*` names are reserved for this return-protocol family,
kept distinct from concurrent suite extensions. They cover scalar (including
`0.1 + 0.2`), all supported map/list overloads, nested Json and primitive/null
fields, copies after mutation, body plus repeated entries, preserved int entry
HALT results, partial-entry failure, application failure and invalid root/value
writes. `coverage.json` supplies independent expected payloads; an unset success
has null. All 24 return imports are reached by compiled programs.

Corpus source wrappers use `_lmcode_ ... out=ARGV[0]`; they do not execute a host
or use retired `savedsl`. Regenerate with the mono build named above, rebuild the
reference C++ sample, run `record.py` once, review that old diagnostics are
unchanged except for null frames, then sync the exact committed suite into ports.
