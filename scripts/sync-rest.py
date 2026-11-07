#!/usr/bin/env python3
"""Copy the shared REST conformance suite (the opt-in `rest` std module) from the spec repository and pin it.

  python scripts/sync-rest.py            copy ../lmcode/tests/rest-suite (or $LMCODE_SPEC_DIR) and write rest-suite.lock
  python scripts/sync-rest.py --verify   check conformance/rest-suite against the lock

Portable digest: sha256 over rows "<sha256(file)>  <relative path>\\n", paths sorted bytewise (C locale).
"""
from __future__ import annotations
import hashlib, os, pathlib, shutil, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = pathlib.Path(os.environ.get("LMCODE_SPEC_DIR", ROOT.parent / "lmcode")).resolve()
DEST = ROOT / "conformance" / "rest-suite"
LOCK = ROOT / "rest-suite.lock"


def digest(directory):
    rows = []
    for path in directory.rglob("*"):
        if path.is_file():
            rows.append((path.relative_to(directory).as_posix().encode("utf-8"), hashlib.sha256(path.read_bytes()).hexdigest()))
    rows.sort()
    return hashlib.sha256(b"".join(h.encode() + b"  " + n + b"\n" for n, h in rows)).hexdigest()


def forget(function, path, _info):
    os.chmod(path, 0o700)
    function(path)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        text = LOCK.read_text(encoding="utf-8")
        expected = next((l.split("=", 1)[1] for l in text.splitlines() if l.startswith("sha256=")), "")
        actual = digest(DEST) if DEST.is_dir() else ""
        if not expected or actual != expected:
            raise SystemExit("conformance/rest-suite digest " + actual + " differs from " + expected)
        print("conformance/rest-suite matches " + next(l.split("=", 1)[1] for l in text.splitlines() if l.startswith("commit=")))
        return
    source = SOURCE / "tests" / "rest-suite"
    if not source.is_dir():
        raise SystemExit("canonical rest-suite missing: " + str(source))
    commit = subprocess.check_output(["git", "-C", str(SOURCE), "rev-parse", "HEAD"], text=True).strip()
    if DEST.exists():
        shutil.rmtree(DEST, onerror=forget)
    DEST.mkdir(parents=True)
    for path in sorted(source.rglob("*")):
        if path.is_file():
            target = DEST / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())  # contents only: no mode bits, no newline translation
    LOCK.write_bytes(("repo=https://github.com/lmctl-ai/lmcode\ncommit=" + commit + "\nsha256=" + digest(DEST) + "\n").encode("utf-8"))
    print("synced REST suite from lmcode " + commit)


if __name__ == "__main__":
    main()
