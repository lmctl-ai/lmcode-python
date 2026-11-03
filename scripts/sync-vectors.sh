#!/usr/bin/env bash
# Generate core bytecode from mono's compiler sources and pin the shared C++ runtime vectors.
set -eu
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MONO="${LMCODE_MONO:-$HERE/../lmctl-mono-wp157}"
CPP="${LMCODE_CPP_DIR:-$HERE/../lmcode-cpp-wp165-ref}"
PYTHON="${PYTHON:-python3}"
command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=python
core="$HERE/conformance/vectors"
digest() { "$PYTHON" - "$1" <<'PY'
import hashlib,pathlib,sys
root=pathlib.Path(sys.argv[1]);rows=[]
for path in sorted(p for p in root.rglob('*') if p.is_file()):
 rel=path.relative_to(root).as_posix();rows.append(hashlib.sha256(path.read_bytes()).hexdigest()+"  ./"+rel+"\n")
print(hashlib.sha256("".join(rows).encode()).hexdigest())
PY
}
if [ "${1:-}" = "--verify" ]; then
  for suite in vectors stdlib-vectors return-vectors invocation-vectors; do
    dir="$HERE/conformance/$suite"; lock="$HERE/$suite.lock"
    [ -d "$dir" ] && [ -s "$lock" ] || { echo "$suite missing; run scripts/sync-vectors.sh" >&2; exit 1; }
    want="$(sed -n 's/^sha256=//p' "$lock")"; have="$(digest "$dir")"
    [ "$want" = "$have" ] || { echo "$suite digest $have differs from $lock" >&2; exit 1; }
    echo "$suite verified ($(find "$dir" -maxdepth 1 -name '*.dslb' | wc -l | tr -d ' ') bytecode vectors)"
  done
  exit 0
fi
mono_commit="$(git -C "$MONO" rev-parse HEAD)"
[ -f "$MONO/lmscript/scripts/generate-dsl-conformance.ts" ] || { echo "mono generator missing at $MONO" >&2; exit 1; }
[ -d "$CPP/conformance/vectors" ] || { echo "lmcode-cpp source missing at $CPP" >&2; exit 1; }
cpp_commit="$(git -C "$CPP" rev-parse HEAD)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
node --experimental-strip-types "$MONO/lmscript/scripts/generate-dsl-conformance.ts" "$TMP/core"
rm -rf "$core"; mkdir -p "$core"; cp -a "$TMP/core/." "$core/"
printf 'source=lmctlhq/lmctl-mono/lmscript\ncommit=%s\nsha256=%s\n' "$mono_commit" "$(digest "$core")" > "$HERE/vectors.lock"
for suite in stdlib-vectors return-vectors invocation-vectors; do
  [ -d "$CPP/conformance/$suite" ] || { echo "lmcode-cpp lacks $suite" >&2; exit 1; }
  dir="$HERE/conformance/$suite"; rm -rf "$dir"; mkdir -p "$dir"; cp -a "$CPP/conformance/$suite/." "$dir/"
  printf 'repo=https://github.com/lmctl-ai/lmcode-cpp\ncommit=%s\nsha256=%s\n' "$cpp_commit" "$(digest "$dir")" > "$HERE/$suite.lock"
done
echo "synced mono core (410 vectors) at $mono_commit and shared std/return/invocation suites from lmcode-cpp $cpp_commit"
