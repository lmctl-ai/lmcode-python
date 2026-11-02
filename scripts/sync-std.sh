#!/usr/bin/env bash
# Pin the canonical schema and docs copied into mono's lmscript workspace.
set -eu
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MONO="${LMCODE_MONO:-$HERE/../lmctl-mono-wp157}"
SRC="$MONO/lmscript/lmcode-std.schema.json"
DOC="$MONO/lmscript/lmcode-std.docs.json"
DST="$HERE/std/lmcode-std.schema.json"
DOC_DST="$HERE/std/lmcode-std.docs.json"
commit="$(git -C "$MONO" rev-parse HEAD)"
if [ "${1:-}" = "--verify" ]; then
  for pair in "std:$DST" "std-docs:$DOC_DST"; do
    lock="$HERE/${pair%%:*}.lock"; file="${pair#*:}"
    [ -f "$file" ] && [ -f "$lock" ] || { echo "$lock missing; run scripts/sync-std.sh" >&2; exit 1; }
    want="$(sed -n 's/^sha256=//p' "$lock")"; have="$(sha256sum "$file" | cut -d' ' -f1)"
    [ "$want" = "$have" ] || { echo "$file differs from $lock" >&2; exit 1; }
  done
  python3 - "$DST" <<'PY'
import json,sys
schema=json.load(open(sys.argv[1],encoding='utf8'))
count=sum(map(len,schema.get('functions',{}).values()))+sum(sum(map(len,t.get('methods',{}).values())) for t in schema.get('types',{}).values())
if count != 206: raise SystemExit(f'canonical standard signature count {count}, expected 206')
print(f'canonical std schema verified: {count} signatures')
PY
  exit 0
fi
[ -f "$SRC" ] && [ -f "$DOC" ] || { echo "canonical std files missing in mono clone $MONO" >&2; exit 1; }
mkdir -p "$HERE/std"
cp "$SRC" "$DST"; cp "$DOC" "$DOC_DST"
printf 'source=lmctlhq/lmctl-mono/lmscript/lmcode-std.schema.json\ncommit=%s\nsha256=%s\n' "$commit" "$(sha256sum "$DST" | cut -d' ' -f1)" > "$HERE/std.lock"
printf 'source=lmctlhq/lmctl-mono/lmscript/lmcode-std.docs.json\ncommit=%s\nsha256=%s\n' "$commit" "$(sha256sum "$DOC_DST" | cut -d' ' -f1)" > "$HERE/std-docs.lock"
echo "synced canonical 206-signature std schema/docs from mono $commit"
