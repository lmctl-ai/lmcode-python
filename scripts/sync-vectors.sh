#!/usr/bin/env bash
# Pin the mono-generated core corpus and the canonical std catalog vector set.
set -eu
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MONO="${LMCODE_MONO:-$HERE/../lmctl-mono-wp157}"
GO_SDK="${LMCODE_GO:-$HERE/../lmcode-go-wp157-ref}"
mono_commit="$(git -C "$MONO" rev-parse HEAD)"
go_commit="$(git -C "$GO_SDK" rev-parse HEAD)"
core="$HERE/conformance/vectors"
stdlib="$HERE/conformance/stdlib-vectors"
digest() { (cd "$1" && find . -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1); }
if [ "${1:-}" = "--verify" ]; then
  for pair in "vectors:$core" "stdlib-vectors:$stdlib"; do
    name="${pair%%:*}"; dir="${pair#*:}"; lock="$HERE/$name.lock"
    [ -d "$dir" ] && [ -s "$lock" ] || { echo "$name missing; run scripts/sync-vectors.sh" >&2; exit 1; }
    want="$(sed -n 's/^sha256=//p' "$lock")"; have="$(digest "$dir")"
    [ "$want" = "$have" ] || { echo "$name differs from $lock" >&2; exit 1; }
    echo "$name verified ($(find "$dir" -maxdepth 1 -name '*.dslb' | wc -l | tr -d ' ') bytecode vectors)"
  done
  exit 0
fi
[ -f "$MONO/lmscript/scripts/generate-dsl-conformance.ts" ] || { echo "mono lmscript generator not found at $MONO" >&2; exit 1; }
[ -d "$GO_SDK/conformance/stdlib-vectors" ] || { echo "standard vector source not found at $GO_SDK" >&2; exit 1; }
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
node --experimental-strip-types "$MONO/lmscript/scripts/generate-dsl-conformance.ts" "$TMP/core"
rm -rf "$core"; mkdir -p "$core"; cp -a "$TMP/core/." "$core/"
rm -rf "$stdlib"; mkdir -p "$stdlib"; cp -a "$GO_SDK/conformance/stdlib-vectors/." "$stdlib/"
printf 'source=lmctlhq/lmctl-mono/lmscript\ncommit=%s\nsha256=%s\n' "$mono_commit" "$(digest "$core")" > "$HERE/vectors.lock"
printf 'source=lmctl-ai/lmcode-go/conformance/stdlib-vectors\ncommit=%s\nsha256=%s\n' "$go_commit" "$(digest "$stdlib")" > "$HERE/stdlib-vectors.lock"
echo "synced mono core vectors from $mono_commit and canonical std vectors from lmcode-go $go_commit"
