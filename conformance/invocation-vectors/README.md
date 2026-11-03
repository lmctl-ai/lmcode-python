# Native invocation goldens

R1 uses untyped compiler-produced lmcode bytecode (DSLB v6). Typed bytecode
fixtures belong to R2. `run_invocations.cpp` loads/runs these programs in one
process with one shared counter and independent program-slot sinks, dispatches
int-returning entries, and writes one envelope. Source schema remains unchanged.

`goldens.py` authors expectations from explicit contract data, never observed
host output. Tests pin every source, binary, input and expected-byte file in
vectors.lock. Private metadata and per-slot copies are created separately for
each run; filenames include spaces/Unicode and parser order is reversed.

Regenerate compiler bytes with a private source compiler library:

```sh
LMCODE_COMPILER_MODULE=/absolute/mono/lmscript/dist/dsl.js node conformance/invocation-vectors/generate.mjs
python3 conformance/invocation-vectors/goldens.py
```

Then `make test-invocation-vectors`. Standalone duplicate filenames, one-slot
builders, single-list payloads, nested/null values and located/global failures
have exact bytes. Malformed metadata, duplicate/missing/extra registrations and
present-empty environment paths must fail before dispatch. No public manifest
flag or script-facing bytecode path accessor is introduced.

Canonical byte regressions include general-format exponent boundaries (-4 and 6),
smallest and adjacent subnormals, signed zero, all 32 ASCII controls and Unicode.
`metadata-errors.json` authors full failure frames for malformed types, missing
fields, unsafe/underflow numbers (including nested pointer paths), UTF-8, BOM,
duplicate keys, overflow and parser errors. `check_metadata.py` is the shared
child-process oracle; comparisons include status, stdout bytes and stderr.

The `dry-null-*` vectors pin the VM boundary before result conversion and host
callback dispatch. They use the per-case `schema` field (including nullable and
nonnullable result contracts), exercise skipped functions/methods, and reject
null arguments/receivers for invoked previews. The object-return, skipped-consumer
and null-receiver source/schema/bytecode are the original WP90 reproducers.
`valid-dry-unknown-root` in `metadata-errors.json` pins the pre-collector dry marker.
