#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="${1:-/tool/formal_tools/oss-cad-suite/bin}"
TARGET_NAME="${2:-enhanced-oss-cad}"
TARGET_PATH="${TARGET_DIR}/${TARGET_NAME}"

mkdir -p "${TARGET_DIR}"
ln -sfn "${ROOT}/formal" "${TARGET_PATH}"

echo "Installed ${TARGET_PATH} -> ${ROOT}/formal"
