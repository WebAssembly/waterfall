# Cmake toolchain description file for the waterfall-built clang wasm toolchain

# This is arbitrary, AFAIK, for now.
cmake_minimum_required(VERSION 3.4.0)

set(CMAKE_SYSTEM_NAME Wasm)
set(CMAKE_SYSTEM_VERSION 1)
set(CMAKE_SYSTEM_PROCESSOR wasm32)
set(triple wasm32-unknown-unknown-wasm)

set(WASM_SDKROOT ${CMAKE_CURRENT_LIST_DIR})
set(CMAKE_C_COMPILER ${WASM_SDKROOT}/bin/clang)
set(CMAKE_CXX_COMPILER ${WASM_SDKROOT}/bin/clang++)
set(CMAKE_AR ${WASM_SDKROOT}/bin/llvm-ar)
set(CMAKE_RANLIB ${WASM_SDKROOT}/bin/llvm-ranlib)
set(CMAKE_C_COMPILER_TARGET ${triple})
set(CMAKE_CXX_COMPILER_TARGET ${triple})

set(CMAKE_SYSROOT ${WASM_SDKROOT}/sysroot)
set(CMAKE_STAGING_PREFIX ${WASM_SDKROOT}/sysroot)

# Don't look in the sysroot for executables to run during the build
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
# Only look in the sysroot (not in the host paths) for the rest
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
