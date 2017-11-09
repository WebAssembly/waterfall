# This is arbitrary, AFAIK, for now.
cmake_minimum_required(VERSION 3.4.0)

set(CMAKE_SYSTEM_NAME Wasm)
set(CMAKE_SYSTEM_VERSION 1)
set(CMAKE_SYSTEM_PROCESSOR wasm32)

set(WASM_SDKROOT /Users/dschuff/code/waterfall/src/work/wasm-install)
set(CMAKE_C_COMPILER ${WASM_SDKROOT}/bin/clang)
set(CMAKE_CXX_COMPILER ${WASM_SDKROOT}/bin/clang++)
set(CMAKE_SYSROOT ${WASM_SDKROOT}/sysroot)
set(CMAKE_STAGING_PREFIX ${WASM_SDKROOT}/sysroot)