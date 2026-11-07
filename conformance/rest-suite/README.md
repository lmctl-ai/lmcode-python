# REST conformance suite (`rest` std module)

Shared by every runtime; see [spec/std-rest.md](../../spec/std-rest.md).

| File | Role |
|---|---|
| `host.schema.json` | host schema = the module's declarations (identical to `std/rest/lmcode-rest.schema.json`; CI checks) |
| `app.lms` | the program: 13 routes, 13 handlers, `rest_serve()` |
| `app.dslb` | `app.lms` compiled with the published `@lmctl-ai/lmctl` (DSLB v6); `node build.mjs` regenerates it |
| `scenarios.json` | `options` (`max_body_bytes`), `stream`, `fatal`, `silent` (below) |

## Running it in a runtime

Register std **and** rest, load `app.dslb` against the bytes of `host.schema.json`, run the body through the rest controller
with `max_body_bytes` and a fresh state. No network is involved: the controller reads the input stream and writes the output stream.

* **`stream`** – compose each scenario as `METHOD target HTTP/1.1`, `Host: localhost`, its `headers`, `Content-Length` when there is a
  body (`body`, or `body_repeat` = `text` × `count`; also for POST/PUT/PATCH without body), blank line, body. Concatenate **all** of them
  into one input and compare with the one output: parse responses in order by `Content-Length` (a `HEAD` response has no body bytes).
  Per scenario assert `status`, every listed header (names lower-case; `null` = must be absent), `body` exactly when given, and
  that `Content-Length` equals the body length (GET length for `HEAD`). `stops_server` marks the response after which serving ends;
  the scenario with `unanswered: true` is the request that follows it and must produce no output at all (output ends right after
  the `stops_server` response, and `run` has returned).
* **`fatal`** – for each, input = the composed (or `raw`) request followed by a valid `GET /health`; the output must be exactly one
  response matching `expect`, then end.
* **`silent`** – input = `raw`; output must be empty and `run` must return normally.

Run each of the three groups on a fresh controller, once through in-memory streams and once through a real child process
(stdin/stdout pipes) of a small serve host.

## Pinning

Runtimes copy this directory (all files) to their conformance fixtures and record a lock. Portable digest: sha256 over rows
`<sha256(file)>  <relative path>\n`, paths sorted **bytewise**; in shell:
`(cd DIR && find . -type f -printf '%P\n' | LC_ALL=C sort | xargs sha256sum) | sha256sum`. Mark the fixtures `-text`/binary in
`.gitattributes` (`*.dslb`, and no CRLF conversion for the JSON/lms files) so Windows checkouts keep the bytes.
