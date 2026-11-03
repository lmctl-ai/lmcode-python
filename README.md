# lmcode-python

`lmcode-python` is a pure-Python runtime and host SDK for lmcode bytecode v6. It loads and verifies bytecode against the exact schema bytes used at compile time, then executes the verified program in a synchronous host VM. The wheel is pure Python (`py3-none-any`) with no runtime dependencies or native build step.

## Install and run

```sh
python -m pip install lmcode-python
```

Use the matching `@lmctl-ai/lmctl` compiler to produce bytecode and its schema. Compilation is separate from running; the SDK does not need Node.js at runtime.

## Embed a host

```python
from pathlib import Path
from lmcode import Context, Registry, load

class Greeter:
    def __init__(self):
        self.messages = []

registry = Registry()  # includes the canonical 206-signature standard catalog
registry.context("greeter", "Greeter")
registry.method(
    "Greeter", "say", ["string"], "void",
    lambda context, receiver, args: receiver.messages.append(args[0]),
)
schema = Path("sample.schema.json").read_bytes()
program = load(Path("program.lmcode").read_bytes(), schema, registry)
context = Context()
context.set("greeter", Greeter())
program.run(context, registry)
```

Register functions with `Registry.function(name, params, returns, callback)` and methods with `Registry.method(owner, name, params, returns, callback)`. Callbacks receive the run context, receiver (for methods), and arguments. String callbacks receive UTF-8 text after boundary validation; `raw_strings=True` opts a callback into byte strings. Python `int` preserves all values while VM integer operations wrap to signed 64-bit.

## Dry mode and result frames

A host callback has no dry slot by default: dry execution skips it and returns a fresh dummy matching its declared return type. Use `dry(callback)` for a preview or `dry(real)` to explicitly reuse the real callback. `Context.dry()` reports the current mode. Dry mode does not simulate external effects.

`InvocationResults.from_command()` reads the optional version 1 manifest from `LMCODE_INVOCATION_FILE`; each manifest includes a boolean `dry` field. Select one `ResultSink` per part, run the program and selected entries, then complete or fail the slot. `write_frame()` emits one terminal `LMCODE_RETURN_BEGIN` / `LMCODE_RETURN_END` frame after dispatch. The sink owns JSON-compatible results and enforces an optional schema result contract.

## Sample host

The repository includes a Shop/Ledger host in `sample/main.py` and a `lmcode-python-sample` entry point. It supports `--version`, `--lmcode-schema`, `--lmcode-schema --json`, `--lmcode-signatures`, and repeated `--lmcode FILE`, `--first FILE`, and `--last FILE` pairs.

```sh
python -m sample.main --version
python -m sample.main --lmcode sample-suite/corpus/bytecode/001-literals.dslb
```

## Development checks

```sh
bash scripts/sync-std.sh --verify
bash scripts/sync-vectors.sh --verify
python scripts/sync-sample-suite.py --verify
python -m unittest discover -s tests
python scripts/check-verifier-mutations.py
python -m lmcode.conformance conformance/vectors
python -c 'from lmcode.conformance import run_suite; raise SystemExit(run_suite("conformance/stdlib-vectors", True))'
python scripts/run-return-vectors.py
python scripts/run-invocation-vectors.py
LMCODE_COMPILER=/path/to/lmscript python scripts/run-sample-suite.py
```

The sync scripts pin the mono-generated core corpus and standard schema/docs, the shared standard/result/invocation vectors, and the sample suite. Locks record source revisions and SHA-256 digests. The 271 standard vectors include successful executions beyond the former string-size, matcher-work, and collection-count boundaries. The VM adds no execution or memory budgets.

GitHub Actions run the test, mutation, conformance, and sample suites on Ubuntu, macOS, and Windows. The workflow installs the latest `@lmctl-ai/lmctl` locally for compile checks. CI does not publish Python packages or create release tags.
