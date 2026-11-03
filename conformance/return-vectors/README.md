# Original return boundary fixtures

These nine untyped compiler-produced lmcode bytecodes (DSLB v6) retain their
original instructions, HALT values, schema binding and source positions. The
fixture host now uses the canonical invocation collector and emits one success
or controlled-failure envelope. All 24 imports are checked after execution.

`payloads.json` records the authored success values. The envelope generator uses
those values and authored error/source positions, never host output. The virtual
header is one line, preserving the original compiled location offsets.

```sh
LMCODE_COMPILER_MODULE=/absolute/mono/lmscript/dist/dsl.js node conformance/return-vectors/generate.mjs
```

`make conformance` always executes the fixture host; there is no harness skip.
The old public export wrapper is removed. Fault hosts deliberately reset state,
emit prematurely or use a lossy formatter; their output is refused by the oracle.
