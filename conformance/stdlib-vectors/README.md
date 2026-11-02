# Standard and optional catalog vectors

The 16 string vectors cover all 16 functions in
`stdlib/string.schema-fragment.json`, plus negative/oversized repeat failures.
Run `make conformance` to run both the core and catalog suites.

Each `NAME.dsl` is a lmcode body; its `.dslb` is compiled, not hand-assembled.
`NAME.expect` and `manifest.json` record independently specified expectations.
The host contract is in the manifest: `bytes(hex)` supplies arbitrary bytes and
`t.hex(value)` records lowercase hexadecimal, avoiding source-encoding and
newline ambiguities. Invalid UTF-8, embedded NUL, and partial UTF-8 slices must
remain bytes in every SDK. The helper does not decode or normalize text.

Recompile using a matching version-6 compiler from the repository root:

```sh
python3 conformance/compile-vectors.py conformance/stdlib-vectors
make conformance
```

Set `LMSCRIPT_BIN` to choose the compiler and `TMPDIR` to choose scratch storage.
The wrapper places one line before the source body; source-located errors thus
refer to body line plus one. Expectations are never regenerated from VM output.
The catalog suite is separate from the 61 core runtime vectors so SDKs can
adopt functions independently without silently skipping the core contract.

## File catalog

The 16 `file-*` vectors use `file.schema.json` and the runner's
`test_temp_dir() -> string` fixture. The runner creates a fresh directory for
each case and removes it afterward. File content is checked as bytes; the
large case writes 1,200,000 bytes, and the line cases preserve CR bytes and
final empty fields. Unicode filenames and paths longer than 260 characters are
covered by `test_long_path() -> string`, which creates nested directories and
returns an ordinary absolute path. Both fixtures belong only to the test host
schema. Cleanup also runs after load or execution failures.

`runtime_error_file` has three payload lines: `RUN_HOST`, the function name,
and the path relative to `test_temp_dir()` (an empty path means the directory
itself). The runner expands that path, then requires the error to begin with
`FUNCTION: ABSOLUTE_PATH: ` and to have a nonempty OS reason suffix. This
keeps function/path behavior portable while allowing localized OS diagnostics.

The additional 11 `math-*` vectors use `math.schema.json` to cover all 16 integer/float overloads in `stdlib/math.schema-fragment.json`. These string and math groups contain 29 vectors. Expectations check wrapping integer powers, exact floor roots near int64 limits, signed zero, NaN propagation and halfway-away rounding. Domain failures assert `RUN_HOST` with source positions. Non-exact finite libm results use the ordinary approximate trace format. The compiler only accepts integer literals through 2^53, so boundary inputs are constructed using exact wrapping integer expressions rather than oversized literals.

## Collections and testing

The 31 additional collection/testing vectors use `collections.schema.json`;
the complete suite contains 271 vectors (74 base catalog, 38 v3 codec/snapshot,
112 data-contract, and 47 seeded byte/property cases). They cover every list/map
method, mutation chaining, insertion order, replacement without reordering,
removal with index shifting, raw-byte keys/values, NaN lookup, empty iteration,
split edge cases, and allocations beyond the former shared object-count budget. Each vector starts
with a fresh collection arena. The core suite's legacy `IntList` fixture must
not be registered alongside the collection catalog's methods.

Testing is explicitly registered and declared by this test host; it is not
part of built-in std. `print` writes raw bytes plus LF to a captured sink. The fixture-only
`printed() -> string` returns that entire sink without decoding; `t.hex`
checks the result. Assertion vectors cover tolerance boundaries, NaNs,
negative tolerance and equal infinities.

`runtime_error_exact` has two payload lines: error code, then complete base
message. The runner requires a successful load and failed run, strips only
an SDK-generated source prefix using the error's location metadata, and checks
the remainder for exact equality. This differs from the older substring modes
and pins the collection bounds, missing-key and assertion error contracts.

## Seeded property corpus

The 41 `fuzz-*` cases use seeds 7, 42 and 20261024, with 16 rounds per seed,
plus independent trap cases and a 1,200,005-byte file round-trip.
`scripts/gen-std-corpus.py` derives exact expectations from Python byte operations,
ordered dictionaries, and independent numeric/glob rules, never from SDK output.
The compiler produces the checked-in bytecode. The C++ conformance target checks
that source, expectations, schema and manifest match the deterministic generator;
every SDK runs the same committed corpus through its normal vector suite.

Setting `LMCODE_TRACE=1` exposes actual runtime observations for differential
comparison. `scripts/diff-stdlib.py` builds all four runners, verifies the oracle,
and byte-compares their trace/error records; `--large` uses 16 seeds and 64 rounds
per seed. Compiler/build output is kept outside the comparison.
