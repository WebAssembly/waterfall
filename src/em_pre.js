var Module = {}

Module['onAbort'] = function(reason) {
  // d8 does not exit with status 1 when a promise throws. Emscripten calls
  // abort when a wasm module fails to initialize, which is implemented in JS
  // as a function that terminates execution by throwing an exception.
  // Emscripten's abort has an 'onAbort' hook, so we can use that to call d8's
  // quit, which correctly returns an error code even from a promis.
  quit(1);
};
