# Cmake toolchain description file for the waterfall-built clang wasm toolchain

# This is arbitrary, AFAIK, for now.
cmake_minimum_required(VERSION 3.4.0)

set(CMAKE_SYSTEM_NAME Wasm)
set(CMAKE_SYSTEM_VERSION 1)
set(CMAKE_SYSTEM_PROCESSOR wasm32)
set(triple wasm32-unknown-unknown-wasm)

# This file should be installed as $SDKROOT/cmake/Modules/Platform/Wasm.cmake.
# That suppresses noisy CMake warnings: "System is unknown to cmake"
get_filename_component(WASM_SDKROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)

list(APPEND CMAKE_MODULE_PATH "${WASM_SDKROOT}/cmake/Modules")


if (CMAKE_HOST_WIN32)
        set(EXE_SUFFIX ".exe")
else()
        set(EXE_SUFFIX "")
endif()
if ("${CMAKE_C_COMPILER}" STREQUAL "")
  set(CMAKE_C_COMPILER ${WASM_SDKROOT}/bin/clang${EXE_SUFFIX})
endif()
if ("${CMAKE_CXX_COMPILER}" STREQUAL "")
  set(CMAKE_CXX_COMPILER ${WASM_SDKROOT}/bin/clang++${EXE_SUFFIX})
endif()
if ("${CMAKE_AR}" STREQUAL "")
  set(CMAKE_AR ${WASM_SDKROOT}/bin/llvm-ar${EXE_SUFFIX} CACHE FILEPATH "llvm ar")
endif()
if ("${CMAKE_RANLIB}" STREQUAL "")
 set(CMAKE_RANLIB ${WASM_SDKROOT}/bin/llvm-ranlib${EXE_SUFFIX} CACHE FILEPATH "llvm ranlib")
endif()
set(CMAKE_C_COMPILER_TARGET ${triple})
set(CMAKE_CXX_COMPILER_TARGET ${triple})
set(CMAKE_REQUIRED_FLAGS --target=${triple})


set(CMAKE_SYSROOT ${WASM_SDKROOT}/sysroot)
set(CMAKE_STAGING_PREFIX ${WASM_SDKROOT}/sysroot)

# Don't look in the sysroot for executables to run during the build
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
# Only look in the sysroot (not in the host paths) for the rest
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
