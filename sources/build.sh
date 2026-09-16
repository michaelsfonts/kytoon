#!/usr/bin/env bash
#
# Build all Kytoon One binaries: otf, ttf, woff2, woff.
#
#   ./sources/build.sh        (run from anywhere)
#
# Steps:
#   1. Heal features.fea after a bad Glyphs export: restore a blanked
#      @Uppercase class, and repair the frac feature if Glyphs hoisted its
#      rules into a Prefix block. Either one otherwise kills the build.
#   2. Build otf / ttf / woff2 via gftools-builder (venv/bin is put on PATH so
#      the fontmake subprocess it spawns is found).
#   3. Generate the woff (gftools only emits woff2).
#
set -euo pipefail
cd "$(dirname "$0")"

VENV="$PWD/venv/bin"
export PATH="$VENV:$PATH"

echo "==> Guard: check @Uppercase class"
"$VENV/python3" fix_features.py

echo "==> Build otf / ttf / woff2"
"$VENV/gftools-builder" config.yaml

echo "==> Generate woff"
"$VENV/python3" - <<'PY'
from fontTools.ttLib import TTFont
f = TTFont("../fonts/ttf/KytoonOne-Regular.ttf")
f.flavor = "woff"
f.save("../fonts/webfonts/KytoonOne-Regular.woff")
print("woff generated")
PY

echo "==> Done: fonts/{otf,ttf,webfonts}/KytoonOne-Regular.*"
