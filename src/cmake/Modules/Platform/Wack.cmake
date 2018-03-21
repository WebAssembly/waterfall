# WACK (WebAssembly Clang Kit) is an experimental WebAssembly standalone
# toolchain.

# This is arbitrary, AFAIK, for now.
cmake_minimum_required(VERSION 3.4.0)

set(CMAKE_SYSTEM_VERSION 1)
set(CMAKE_SYSTEM_PROCESSOR wasm32)
set(triple wasm32-unknown-unknown-wasm)

# Make HandleLLVMOptions.cmake happy.
# TODO(sbc): We should probably fix llvm or libcxxabi instead.
# See: https://reviews.llvm.org/D33753
set(UNIX 1)

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
