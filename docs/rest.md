# REST server over stdio (`rest` std module)

Opt-in module of [spec/std-rest.md](https://github.com/lmctl-ai/lmcode/blob/main/spec/std-rest.md). There is **no network
listener**: the host process reads HTTP/1.1 requests from stdin and writes responses to stdout. `Registry()` does not register it
(the default catalog stays at 206 signatures).

```python
from pathlib import Path
from lmcode import Registry, load
from lmcode.rest import register_rest

registry = Registry()
rest = register_rest(registry, max_body_bytes=1 << 20,            # input/output default to sys.stdin.buffer / sys.stdout.buffer
                     on_handler_error=lambda entry, message: print(entry, message, file=__import__("sys").stderr))
program = load(Path("app.dslb").read_bytes(), Path("host.schema.json").read_bytes(), registry)  # schema includes lmcode-rest.schema.json
rest.run(program)   # body: rest_route(...) then rest_serve(); then serves until EOF / rest_stop() / a framing error
```

Try it without writing any host code:

```sh
printf 'GET /health HTTP/1.1\r\nHost: x\r\n\r\n' | python -m lmcode.rest conformance/rest-suite/app.dslb conformance/rest-suite/host.schema.json
```

`python -m lmcode.rest PROGRAM.dslb HOST.schema.json [--max-body-bytes N]` exits 0 after serving, 2 on bad usage, 3 on a load or run error.

* `register_rest(registry, input=None, output=None, max_body_bytes=1048576, on_handler_error=None)` returns the controller; it raises
  `LOAD_UNBOUND` if the module is already registered in that registry.
* `rest.dispatch(Request(method, target, headers, body))` returns a `Response(status, headers, body)`; it is the transport-independent core used by the unit tests.
* Streams are binary file-like objects (`read1`/`read`, `write`, `flush`); every response is flushed before the next request is read.
* Keep stdout clean while serving: `print` and diagnostics belong on stderr.
* Tests: `python -m unittest discover -s tests` (`tests/test_rest.py`), `python scripts/run-rest-suite.py` (shared suite, in-memory and via a child process),
  `python scripts/sync-rest.py --verify` (suite pin; run without `--verify` to re-copy from `../lmcode`).
