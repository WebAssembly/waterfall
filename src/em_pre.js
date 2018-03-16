var Module = {}

Module['onAbort'] = function(reason) {
  // JS shells do not exit with status 1 when a promise is rejected. Emscripten
  // calls abort when a wasm module fails to initialize, which is implemented in
  // JS as a function that terminates execution by throwing an exception, which
  // causes the instantiate promise to be rejected, which causes the shell to
  // falsely return 0.
  // Emscripten's abort has an 'onAbort' hook, so we can use that to call d8's
  // quit, which correctly returns an error code even from a promise.
  quit(1);
};
