#!/bin/bash
# Wrapper script for emcc/em++
#
# The intent of this scripts is to provide entry points into a pre-baked
# toolchain that is not configured via EM_CONFIG or $HOME/.emscripten, but
# worked out-of-the-box with a builtin configuration file.
# Technically it is still possible to override this with --em-config on the
# command line.

SCRIPT_FILE=$(readlink -f "${BASH_SOURCE}")
SCRIPT_DIR=$(cd $(dirname "${SCRIPT_FILE}") && pwd)
WASM_ROOT=$(dirname "${SCRIPT_DIR}")

# Without this emscripten will attempt to write a '_santiy' config file to the
# toolchain root, which will fail because it's not a writable location.
export EMCC_SKIP_SANITY_CHECK=1

# Use fastcomp backend unless EMCC_WASM_BACKEND is set to 1.
if [[ $EMCC_WASM_BACKEND == 1 ]]; then
  export EM_CONFIG="${WASM_ROOT}/emscripten_config_upstream"
else
  export EM_CONFIG="${WASM_ROOT}/emscripten_config_fastcomp"
fi

exec "${WASM_ROOT}/emscripten/$(basename $0)" "$@"
