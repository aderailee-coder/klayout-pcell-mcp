#!/usr/bin/env bash
# Wrapper script: convert Laker TF on the fly and open GDS in KLayout
#
# Usage:
#   ./tools/open_with_laker_tf.sh /path/to/process.tf /path/to/design.gds [TechName]

set -e

TF="$1"
GDS="$2"
TECH_NAME="${3:-LakerProcess}"
OUT_DIR="/tmp/klayout_tech_${TECH_NAME}"

if [ -z "$TF" ] || [ -z "$GDS" ]; then
  echo "Usage: $0 <laker.tf> <design.gds> [tech_name]"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"

echo "Converting Laker TF → KLayout technology..."
"$PYTHON" "$SCRIPT_DIR/laker_tf_to_klayout.py" \
  --tf "$TF" \
  --out-dir "$OUT_DIR" \
  --tech-name "$TECH_NAME" \
  --gds "$GDS"

# Install technology (user-level)
mkdir -p "$HOME/.klayout/tech/$TECH_NAME"
cp -f "$OUT_DIR"/* "$HOME/.klayout/tech/$TECH_NAME/"

echo "Opening GDS with technology: $TECH_NAME"
exec klayout "$GDS" -t "$TECH_NAME"
