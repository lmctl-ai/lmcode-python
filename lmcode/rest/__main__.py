"""Serve a compiled program's REST routes over stdin/stdout (no network).

    python -m lmcode.rest PROGRAM.dslb HOST.schema.json [--max-body-bytes N]

stdout carries only HTTP responses; handler failures go to stderr. Exit status: 0 after serving, 2 usage, 3 error.
"""
import sys
from pathlib import Path
from .. import LmcodeError, Registry, load
from . import register_rest


def main(argv):
    args = list(argv)
    if len(args) not in (2, 4) or (len(args) == 4 and (args[2] != "--max-body-bytes" or not args[3].isdigit())):
        sys.stderr.write("usage: python -m lmcode.rest PROGRAM.dslb HOST.schema.json [--max-body-bytes N]\n")
        return 2
    try:
        registry = Registry()
        options = {"max_body_bytes": int(args[3])} if len(args) == 4 else {}
        rest = register_rest(registry, **options)
        program = load(Path(args[0]).read_bytes(), Path(args[1]).read_bytes(), registry)
        rest.run(program)
    except (LmcodeError, OSError) as error:
        sys.stderr.write("lmcode.rest: " + str(error) + "\n")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
