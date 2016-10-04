#!/bin/bash

SCRIPT_FILE=$(readlink -f "${BASH_SOURCE}")
SCRIPT_DIR=$(cd $(dirname "${SCRIPT_FILE}") && pwd)
WASM_ROOT=$(dirname "${SCRIPT_DIR}")

export EMCC_SKIP_SANITY_CHECK=1
export EM_CONFIG="${WASM_ROOT}/emscripten_config"

exec "${WASM_ROOT}/emscripten/$(basename $0)" $*
