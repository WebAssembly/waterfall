#!/bin/bash

SCRIPT_FILE=$(readlink -f "${BASH_SOURCE}")
SCRIPT_DIR=$(cd $(dirname "${SCRIPT_FILE}") && pwd)

export EMCC_SKIP_SANITY_CHECK=1
export EM_CONFIG=$(dirname "${SCRIPT_DIR}")/emscripten_config

exec $SCRIPT_DIR/emscripten/$(basename $0) $*
