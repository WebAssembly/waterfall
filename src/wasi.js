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

/*
 * Simple implmentation of WASI in JS in order to support running of tests
 * with minimal system dependencies such as the GCC torture tests.
 *
 * This script is designed to run under both d8 and nodejs.
 *
 * Usage: wasi.js <wasm_binary>
 */

const PAGE_SIZE = (64 * 1024);
var heap_size_bytes = 16 * 1024 * 1024;
var heap_size_pages = heap_size_bytes / PAGE_SIZE;
var default_memory = new WebAssembly.Memory({initial: heap_size_pages, maximum: heap_size_pages})
var heap;
var heap_uint8;
var heap_uint16;
var heap_uint32;

if (typeof process === 'object' && typeof require === 'function') { // This is node.js
  // Emulate JS shell behavior used below
  const nodeFS = require('fs');
  const nodePath = require('path');
  var read = function(file_path) {
    filename = nodePath['normalize'](file_path);
    return nodeFS['readFileSync'](filename);
  }
  var print = console.log;
  arguments = process['argv'].slice(2);
}

// Exceptions
function TerminateWasmException(value, code) {
  this.stack = (new Error()).stack;
  this.value = value;
  this.exit_code = code;
  this.message = 'Terminating WebAssembly';
  this.toString = function() { return this.message + ': ' + this.value; };
}

function NotYetImplementedException(what) {
  this.stack = (new Error()).stack;
  this.message = 'Not yet implemented';
  this.what = what;
  this.toString = function() { return this.message + ': ' + this.what; };
}

// Heap access helpers.
function setHeap(m) {
  memory = m
  heap = m.buffer
  heap_uint8 = new Uint8Array(heap);
  heap_uint16 = new Uint16Array(heap);
  heap_uint32 = new Uint32Array(heap);
  heap_size_bytes = heap.byteLength;
}

function checkHeap() {
  if (heap.byteLength == 0) {
    setHeap(main_module.exports.memory);
  }
}

function readChar(ptr) {
  return String.fromCharCode(heap_uint8[ptr]);
}

function readStr(ptr, len = -1) {
  var str = '';
  var end = heap_size_bytes;
  if (len != -1)
    end = ptr + len;
  for (var i = ptr; i < end && heap_uint8[i] != 0; ++i)
    str += readChar(i);
  return str;
}

function writeStr(offset, str) {
  var start = offset;
  for (var i = 0; i < str.length; i++ ) {
    write8(offset, str.charCodeAt(i));
    offset++;
  }
  write8(offset, 0);
  offset++;
  return offset - start;
}

function write8(offset, value) { heap_uint8[offset] = value; }
function write16(offset, value) { heap_uint16[offset>>1] = value; }
function write32(offset, value) { heap_uint32[offset>>2] = value; }

function write64(offset, valueFirst, valueLast) {
  heap_uint32[(offset+0)>>2] = valueFirst;
  heap_uint32[(offset+4)>>2] = valueLast;
}

function read8(offset) { return heap_uint8[offset]; }
function read16(offset) { return heap_uint16[offset>>1]; }
function read32(offset) { return heap_uint32[offset>>2]; }

var stdio = (function() {
  var stdout_buf = '';
  return {
    stdoutWrite: function(str) {
      stdout_buf += str;
    },
    stdoutFlush: function() {
      if (stdout_buf[-1] = '\n')
        stdout_buf = stdout_buf.slice(0, -1);
      print(stdout_buf); stdout_buf = '';
    }
  }
})();

// WASI implemenation
// See: https://github.com/WebAssembly/WASI/blob/master/design/WASI-core.md
var wasi_unstable = (function() {
  var DEBUG = false;

  // Dummy environment
  var ENV = {
    USER: 'alice',
  };

  var STDIN  = 0;
  var STDOUT = 1;
  var STDERR = 2;
  var MAXFD  = 2;

  var WASI_ESUCCESS = 0;
  var WASI_EBADF    = 8;
  var WASI_EPERM    = 63;

  var WASI_FILETYPE_UNKNOWN          = 0;
  var WASI_FILETYPE_BLOCK_DEVICE     = 1;
  var WASI_FILETYPE_CHARACTER_DEVICE = 2;

  var WASI_FDFLAG_APPEND   = 0x0001;
  var WASI_FDFLAG_DSYNC    = 0x0002;
  var WASI_FDFLAG_NONBLOCK = 0x0004;
  var WASI_FDFLAG_RSYNC    = 0x0008;
  var WASI_FDFLAG_SYNC     = 0x0010;

  function isValidFD(fd) {
    return fd >= 0 && fd <= MAXFD;
  }

  function trace(function_name, args) {
    if (DEBUG)
      print('wasi_unstable.' + function_name + '(' + Array.from(args) + ')');
  }

  return {
    proc_exit: function(code) {
      trace('proc_exit', arguments);
      throw new TerminateWasmException('wasi_unstable.proc_exit(' + code + ')', code);
    },
    environ_sizes_get: function(environ_count_out_ptr, environ_buf_size_out_ptr) {
      trace('environ_sizes_get', arguments);
      checkHeap();
      var names = Object.getOwnPropertyNames(ENV);
      var total_space = 0;
      for (var i in names) {
        var name = names[i];
        var value = ENV[name];
        // Format of each env entry is name=value with null terminator.
        total_space += name.length + value.length + 2;
      }
      write64(environ_count_out_ptr, 0, names.length);
      write64(environ_buf_size_out_ptr, 0, total_space)
      return WASI_ESUCCESS;
    },
    environ_get: function(environ_pointers_out, environ_out) {
      trace('environ_get', arguments);
      var names = Object.getOwnPropertyNames(ENV);
      for (var i in names) {
        write32(environ_pointers_out, environ_out);
        environ_pointers_out += 4;
        var name = names[i];
        var value = ENV[name];
        var full_string = name + "=" + value;
        environ_out += writeStr(environ_out, full_string);
      }
      write32(environ_pointers_out, 0);
      return WASI_ESUCCESS;
    },
    args_sizes_get: function(args_count_out_ptr, args_buf_size_out_ptr) {
      trace('args_sizes_get', arguments);
      checkHeap();
      write64(args_count_out_ptr, 0, 0);
      write64(args_buf_size_out_ptr, 0, 0)
      return 0;
    },
    args_get: function(args_pointers_out, args_out) {
      trace('args_get', arguments);
      throw new TerminateWasmException('1');
    },
    fd_pread: function(fd, iovs, iovs_len, offset, nread) {
      trace('fd_pread', arguments);
      if (fd != STDIN)
        return WASI_EBADF;
      return WASI_ESUCCESS;
    },
    fd_prestat_get: function(fd, prestat_ptr) {
      trace('fd_prestat_get', arguments);
      checkHeap();
      if (!isValidFD(fd))
        return WASI_EBADF;
      write8(prestat_ptr, WASI_FILETYPE_CHARACTER_DEVICE);
      write16(prestat_ptr+2, WASI_FDFLAG_APPEND);
      write64(prestat_ptr+8, 0);
      write64(prestat_ptr+16, 0);
      return 0;
    },
    fd_prestat_dir_name: function(fd, path_ptr, path_len) {
      trace('fd_prestat_dir_name', arguments);
      if (!isValidFD(fd))
        return WASI_EBADF;
      return 0;
    },
    fd_fdstat_get: function(fd, fdstat_ptr) {
      trace('fd_fdstat_get', arguments);
      if (!isValidFD(fd))
      if (!isValidFD(fd))
        return WASI_EBADF;
      write8(fdstat_ptr, WASI_FILETYPE_CHARACTER_DEVICE);
      write16(fdstat_ptr+2, WASI_FDFLAG_APPEND);
      write64(fdstat_ptr+8, 0);
      write64(fdstat_ptr+16, 0);
      return WASI_ESUCCESS;
    },
    fd_fdstat_set_flags: function(fd, fdflags) {
      trace('fd_fdstat_set_flags', arguments);
      if (!isValidFD(fd))
        return WASI_EBADF;
      return WASI_ESUCCESS;
    },
    fd_read: function(fd, iovs_ptr, iovs_len, nread) {
      trace('fd_read', arguments);
      write32(nread, 0);
      return WASI_ESUCCESS;
    },
    fd_write: function(fd, iovs_ptr, iovs_len, nwritten) {
      trace('fd_write', arguments);
      if (fd != STDOUT && fd != STDERR)
        return WASI_EBADF
      var total = 0;
      for (var i = 0; i < iovs_len; i++) {
        var buf = read32(iovs_ptr); iovs_ptr += 4;
        var len = read32(iovs_ptr); iovs_ptr += 4;
        stdio.stdoutWrite(readStr(buf, len));
        total += len;
      }
      write32(nwritten, total);
      return WASI_ESUCCESS;
    },
    fd_close: function(fd) {
      trace('fd_close', arguments);
      if (!isValidFD(fd))
        return WASI_EBADF;
      return 0;
    },
    fd_seek: function(fd, offset, whence, newoffset_ptr) {
      trace('fd_seek', arguments);
      return WASI_ESUCCESS;
    },
    path_open: function(dirfd, dirflags, path, path_len, oflags, fs_rights_base, fs_rights_inheriting, fs_flags, fd_out) {
      trace('path_open', arguments);
      print("path_open: " + dirfd + " " + readStr(path, path_len));
      return WASM_EPERM;
    },
    path_unlink_file: function(dirfd, path, path_len) {
      trace('path_unlink_file', arguments);
      print("path_unlink_file: " + dirfd + " " + readStr(path, path_len));
      return WASM_EPERM;
    },
    path_remove_directory: function(dirfd, path, path_len) {
      trace('path_remove_directory', arguments);
      print("path_remove_directory: " + dirfd + " " + readStr(path, path_len));
      return WASM_EPERM;
    }
  }
})();

var ffi = (function() {
  var env = {
    memory: default_memory,
    // Any non-wasi dependencies end up under 'env'.
    // TODO(sbc): Implement on the wasm side or add to WASI?
    _Unwind_RaiseException: function() {
      throw new NotYetImplementedException('_Unwind_RaiseException');
    }
  }
  return {
    env: env,
    wasi_unstable: wasi_unstable
  };
})();

if (arguments.length < 1)
  throw new Error('Expected at least one wasm module to load.');

function load_wasm(file_path) {
  const buf = (typeof readbuffer === 'function')
    ? new Uint8Array(readbuffer(file_path))
    : read(file_path, 'binary');
  var instance = new WebAssembly.Instance(new WebAssembly.Module(buf), ffi)
  if (instance.exports.memory) {
    setHeap(instance.exports.memory);
  } else {
    setHeap(default_memory)
  }
  return instance;
}

var main_module_name = arguments[0];
main_module = load_wasm(main_module_name);

if (!(main_module.exports._start instanceof Function))
  throw new Error('_start() not found');

try {
  main_module.exports._start();
  stdio.stdoutFlush();
  print(main_module_name + '::_start() returned normally');
} catch (e) {
  stdio.stdoutFlush();
  if (e instanceof TerminateWasmException) {
    print('Program terminated with: ' + e.exit_code);
    if (e.exit_code != 0) {
      throw e.exit_code;
    }
  } else if (e instanceof NotYetImplementedException) {
    print('NotYetImplemented: ' + e.what);
    throw e;
  } else {
    function is_runtime_trap(e) {
      if ('string' != typeof e) return false;
      var traps = ['unreachable',
                   'memory access out of bounds',
                   'divide by zero',
                   'divide result unrepresentable',
                   'remainder by zero',
                   'integer result unrepresentable',
                   'invalid function',
                   'function signature mismatch'];
      for (var msg in traps) if (e == traps[msg]) return true;
      return false;
    }
    print(is_runtime_trap(e) ?
        ('Runtime trap: ' + e) :
        ('Unknown exception of type `' + typeof(e) + '`: ' + e));
    throw e;
  }
}
