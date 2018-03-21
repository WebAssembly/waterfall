# WACK (WebAssembly Clang Kit) is an experimental WebAssembly standalone
# toolchain. It is used on the build waterfall for testing various toolchain
# components (e.g. clang, LLVM, lld) and engines (e.g. V8 and JSC) but is not
# an official or productionized tool.


# Set up the CMake include path to find the WACK platform file. Following the
# same convention as the CMake distribution suppresses noisy CMake warnings:
# "System is unknown to cmake"
# Module path modification can't be done from the command line, so this file
# exists to do that.

set(WASM_SDKROOT ${CMAKE_CURRENT_LIST_DIR})
list(APPEND CMAKE_MODULE_PATH "${WASM_SDKROOT}/cmake/Modules")

# This has to go before we set CMAKE_SYSTEM_NAME because the default c compiler
# gets set before the platform file is included
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

# Include the platform file
set(CMAKE_SYSTEM_NAME Wack)
