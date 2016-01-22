/*
 * Copyright 2016 WebAssembly Community Group participants
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

// Support JavaScript code to run WebAssembly in a JavaScript shell.

// Emulate <cstdlib>.
var EXIT_SUCCESS = 0;
var EXIT_FAILURE = 1;
var exit_code = 0;

function TerminateWasmException(value) {
  this.value = value;
  this.message = 'Terminating wasm';
  this.toString = function() { return this.message + ': ' + this.value; };
}

function abort() {
  exit_code = EXIT_FAILURE;
  throw new TerminateWasmException('abort()');
}

function exit(code) {
  exit_code = code;
  throw new TerminateWasmException('exit(' + code + ')');
}

var ffi = {
  print: print,
  abort: abort,
  exit: exit,
};

m = _WASMEXP_.instantiateModule(readbuffer(arguments[0]), ffi);

try {
  // The entry point is assumed to be "main".
  m.main();
  print('Program terminated normally.');
} catch (e) {
  if (e instanceof TerminateWasmException) {
    print('Program terminated with: ' + e);
    if (exit_code != EXIT_SUCCESS) {
      throw exit_code;
    }
  } else {
    print('Unknown exception: ' + e);
    throw e;
  }
}
