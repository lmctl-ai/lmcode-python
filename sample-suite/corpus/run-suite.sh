#!/usr/bin/env bash
set -euo pipefail
export LMCODE_SUITE="$(cd "$(dirname "$0")" && pwd)"
exec "${LMSCRIPT_BIN:-lmscript}" "$LMCODE_SUITE/run-suite.lms" "$@"
