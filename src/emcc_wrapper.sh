#!/bin/bash

SCRIPT_FILE=$(readlink -f "${BASH_SOURCE}")
SCRIPT_DIR=$(cd $(dirname "${SCRIPT_FILE}") && pwd)
WASM_ROOT=$(dirname "${SCRIPT_DIR}")

# Without this emscripten will attempt to write an '_santiy' config
# file to the toolchain root, which will fail because its not a
# writable location.
export EMCC_SKIP_SANITY_CHECK=1

# Use fastcomp backend unless EMCC_WASM_BACKEND is set to 1
if [[ $EMCC_WASM_BACKEND == 1 ]]; then
  export EM_CONFIG="${WASM_ROOT}/emscripten_config_vanilla"
else
  export EM_CONFIG="${WASM_ROOT}/emscripten_config"
fi

exec "${WASM_ROOT}/emscripten/$(basename $0)" $*
