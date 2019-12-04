#!/usr/bin/env node
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
let heap_size_bytes = 16 * 1024 * 1024;
let heap_size_pages = heap_size_bytes / PAGE_SIZE;
let default_memory = new WebAssembly.Memory({initial: heap_size_pages, maximum: heap_size_pages})
let heap;
let heap_uint8;
let heap_uint16;
let heap_uint32;

// This is node.js
if (typeof process === 'object' && typeof require === 'function') {
  // Emulate JS shell behavior used below
  var nodeFS = require('fs');
  var nodePath = require('path');
  var read = function(file_path) {
    filename = nodePath['normalize'](file_path);
    return nodeFS['readFileSync'](filename);
  }
  var print = console.log;
  var arguments = process['argv'].slice(2);
  var quit = process.exit
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
  let str = '';
  var end = heap_size_bytes;
  if (len != -1)
    end = ptr + len;
  for (var i = ptr; i < end && heap_uint8[i] != 0; ++i)
    str += readChar(i);
  return str;
}

function writeBuffer(offset, buf) {
  buf.copy(heap_uint8, offset);
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

let DEBUG = false;

function dbg(message) {
  if (DEBUG)
    print(message);
}

// WASI implemenation
// See: https://github.com/WebAssembly/WASI/blob/master/design/WASI-core.md
var wasi_interface = (function() {
  const STDIN  = 0;
  const STDOUT = 1;
  const STDERR = 2;
  const MAXFD  = 2;

  const WASI_ESUCCESS = 0;
  const WASI_EBADF    = 8;
  const WASI_ENOTSUP  = 58;
  const WASI_EPERM    = 63;

  const WASI_PREOPENTYPE_DIR = 0;

  const WASI_LOOKUP_SYMLINK_FOLLOW = 0x1;

  const WASI_FDFLAG_APPEND   = 0x0001;
  const WASI_FDFLAG_DSYNC    = 0x0002;
  const WASI_FDFLAG_NONBLOCK = 0x0004;
  const WASI_FDFLAG_RSYNC    = 0x0008;
  const WASI_FDFLAG_SYNC     = 0x0010;

  const WASI_RIGHT_FD_DATASYNC       = 0x00000001;
  const WASI_RIGHT_FD_READ           = 0x00000002;
  const WASI_RIGHT_FD_SEEK           = 0x00000004;
  const WASI_RIGHT_PATH_OPEN         = 0x00002000;
  const WASI_RIGHT_PATH_FILESTAT_GET = 0x00040000;
  const WASI_RIGHT_FD_READDIR        = 0x00004000;
  const WASI_RIGHT_FD_FILESTAT_GET   = 0x00200000;
  const WASI_RIGHT_ALL               = 0xffffffff;

  const WASI_FILETYPE_UNKNOWN          = 0;
  const WASI_FILETYPE_BLOCK_DEVICE     = 1;
  const WASI_FILETYPE_CHARACTER_DEVICE = 2;
  const WASI_FILETYPE_DIRECTORY        = 3;
  const WASI_FILETYPE_REGULAR_FILE     = 4;
  const WASI_FILETYPE_SOCKET_DGRAM     = 5;
  const WASI_FILETYPE_SOCKET_STREAM    = 6;
  const WASI_FILETYPE_SYMBOLIC_LINK    = 7;

  const WASI_WHENCE_CUR = 0;
  const WASI_WHENCE_END = 1;
  const WASI_WHENCE_SET = 2;

  let env = {
    USER: 'alice',
  };

  let argv = [];

  function trace(syscall_name, syscall_args) {
    if (DEBUG)
      dbg('wasi_snapshot_preview1.' + syscall_name + '(' + Array.from(syscall_args) + ')');
  }

  let stdin = (function() {
    return {
      flush: function() {}
    };
  })();

  let stdout = (function() {
    let buf = '';
    return {
      type: WASI_FILETYPE_CHARACTER_DEVICE,
      flags: WASI_FDFLAG_APPEND,
      write: function(str) {
        buf += str;
        if (buf[-1] == '\n') {
          buf = buf.slice(0, -1);
          print(buf);
          buf = '';
        }
      },
      flush: function() {
        if (buf[-1] == '\n')
          buf = buf.slice(0, -1);
        print(buf);
        buf = '';
      }
    }
  })();

  let stderr = (function() {
    let buf = '';
    return {
      type: WASI_FILETYPE_CHARACTER_DEVICE,
      flags: WASI_FDFLAG_APPEND,
      write: function(str) {
        buf += str;
        if (buf[-1] == '\n') {
          buf = buf.slice(0, -1);
          print(buf);
          buf = '';
        }
      },
      flush: function() {
        if (buf[-1] == '\n')
          buf = buf.slice(0, -1);
        print(buf);
        buf = '';
      }
    }
  })();

  let rootdir = (function() {
    return {
      type: WASI_FILETYPE_DIRECTORY,
      flags: 0,
      flush: function() {},
      name: "/",
      rootdir: "/",
      preopen: true,
      rights_base: WASI_RIGHT_ALL,
      rights_inheriting: WASI_RIGHT_ALL,
    };
  })();

  let openFile = function(filename) {
    dbg('openFile: ' + filename);
    let data = read(filename);
    let position = 0;
    let end = data.length;
    return {
      read: function(len) {
        let start = position;
        let end = Math.min(position + len, data.length);
        position = end;
        return data.slice(start, end)
      },
      seek: function(offset, whence) {
        if (whence == WASI_WHENCE_CUR) {
          position += offset;
        } else if (whence == WASI_WHENCE_END) {
          position += end + offset;
        } else if (whence == WASI_WHENCE_SET) {
          position = offset;
        }
        if (position > end) {
          position = end;
        } else if (position < 0) {
          position = 0;
        }
        return position;
      },
      flush: function() {}
    };
  };

  let openFiles = [
    stdin,
    stdout,
    stderr,
    rootdir,
  ];

  let nextFD = openFiles.length;

  function isValidFD(fd) {
    return openFiles.hasOwnProperty(fd)
  }

  let module_api = {
    proc_exit: function(code) {
      trace('proc_exit', arguments);
      throw new TerminateWasmException('proc_exit(' + code + ')', code);
    },
    environ_sizes_get: function(environ_count_out_ptr, environ_buf_size_out_ptr) {
      trace('environ_sizes_get', arguments);
      checkHeap();
      const names = Object.getOwnPropertyNames(env);
      let total_space = 0;
      for (const i in names) {
        let name = names[i];
        let value = env[name];
        // Format of each env entry is name=value with null terminator.
        total_space += name.length + value.length + 2;
      }
      write64(environ_count_out_ptr, names.length);
      write64(environ_buf_size_out_ptr, total_space)
      return WASI_ESUCCESS;
    },
    environ_get: function(environ_pointers_out, environ_out) {
      trace('environ_get', arguments);
      let names = Object.getOwnPropertyNames(env);
      for (const i in names) {
        write32(environ_pointers_out, environ_out);
        environ_pointers_out += 4;
        let name = names[i];
        let value = env[name];
        let full_string = name + "=" + value;
        environ_out += writeStr(environ_out, full_string);
      }
      write32(environ_pointers_out, 0);
      return WASI_ESUCCESS;
    },
    args_sizes_get: function(args_count_out_ptr, args_buf_size_out_ptr) {
      trace('args_sizes_get', arguments);
      checkHeap();
      let total_space = 0;
      for (const value of argv) {
        total_space += value.length + 1;
      }
      write64(args_count_out_ptr, argv.length);
      write64(args_buf_size_out_ptr, total_space);
      dbg(argv);
      return WASI_ESUCCESS;
    },
    args_get: function(args_pointers_out, args_out) {
      trace('args_get', arguments);
      for (const value of argv) {
        write32(args_pointers_out, args_out);
        args_pointers_out += 4;
        args_out += writeStr(args_out, value);
      }
      write32(args_pointers_out, 0);
      return WASI_ESUCCESS;
    },
    fd_pread: function(fd, iovs, iovs_len, offset, nread) {
      trace('fd_pread', arguments);
      checkHeap();
      if (!isValidFD(fd))
        return WASI_EBADF;
      var file = openFiles[fd];
      if (fd.read == undefined)
        return WASI_EBADF;
      throw new NotYetImplementedException('fd_pread');
    },
    fd_prestat_get: function(fd, prestat_ptr) {
      trace('fd_prestat_get', arguments);
      checkHeap();
      if (!isValidFD(fd))
        return WASI_EBADF;
      var file = openFiles[fd];
      if (!file.preopen)
        return WASI_EBADF;
      write8(prestat_ptr, WASI_PREOPENTYPE_DIR);
      write64(prestat_ptr+4, file.name.length);
      return 0;
    },
    fd_prestat_dir_name: function(fd, path_ptr, path_len) {
      trace('fd_prestat_dir_name', arguments);
      if (!isValidFD(fd))
        return WASI_EBADF;
      var file = openFiles[fd];
      if (!file.preopen)
        return WASI_EBADF;
      write64(path_len, file.name.length);
      writeStr(path_ptr, file.name);
      return 0;
    },
    fd_fdstat_get: function(fd, fdstat_ptr) {
      trace('fd_fdstat_get', arguments);
      if (!isValidFD(fd))
        return WASI_EBADF;
      var file = openFiles[fd];
      write8(fdstat_ptr, file.type);
      write16(fdstat_ptr+2, file.flags);
      write64(fdstat_ptr+8, file.rights_base);
      write64(fdstat_ptr+16, file.rights_inheriting);
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
      if (!isValidFD(fd))
        return WASI_EBADF;
      var file = openFiles[fd];
      if (!file.hasOwnProperty('read'))
        return WASI_EBADF;
      checkHeap();
      let total = 0;
      for (let i = 0; i < iovs_len; i++) {
        let buf = read32(iovs_ptr); iovs_ptr += 4;
        let len = read32(iovs_ptr); iovs_ptr += 4;
        let data = file.read(len);
        if (data.length == 0) {
          break;
        }
        writeBuffer(buf, data);
        total += data.length;
      }
      write32(nread, total);
      return WASI_ESUCCESS;
    },
    fd_write: function(fd, iovs_ptr, iovs_len, nwritten) {
      trace('fd_write', arguments);
      if (!isValidFD(fd))
        return WASI_EBADF;
      var file = openFiles[fd];
      if (!file.hasOwnProperty('write'))
        return WASI_EPERM;
      checkHeap();
      let total = 0;
      for (let i = 0; i < iovs_len; i++) {
        let buf = read32(iovs_ptr); iovs_ptr += 4;
        let len = read32(iovs_ptr); iovs_ptr += 4;
        file.write(readStr(buf, len));
        total += len;
      }
      write32(nwritten, total);
      return WASI_ESUCCESS;
    },
    fd_close: function(fd) {
      trace('fd_close', arguments);
      if (!isValidFD(fd)) {
        return WASI_EBADF;
      }
      openFiles[fd].flush();
      delete openFiles[fd];
      if (fd < nextFD) {
        nextFD = fd;
      }
      return WASI_ESUCCESS;
    },
    fd_seek: function(fd, offset, whence, newoffset_ptr) {
      trace('fd_seek', arguments);
      if (!isValidFD(fd)) {
        return WASI_EBADF;
      }
      let file = openFiles[fd];
      checkHeap();
      let intOffset = parseInt(offset.toString());
      let newPos = file.seek(intOffset, whence);
      write64(newoffset_ptr, newPos);
      dbg("done seek: " + newPos);
      return WASI_ESUCCESS;
    },
    path_filestat_get: function(dirfd, lookupflags, path, path_len, buf) {
      trace('path_filestat_get', arguments);
      if (!isValidFD(dirfd)) {
        return WASI_EBADF;
      }
      let file = openFiles[dirfd];
      if (file != rootdir) {
        return WASI_EBADF;
      }
      let filename = readStr(path, path_len);
      let stat = nodeFS.statSync(filename);
      if (stat.isFile()) {
        write32(buf+16, WASI_FILETYPE_REGULAR_FILE);
      } else if (stat.isSymbolicLink()) {
        write32(buf+16, WASI_FILETYPE_SYMBOLIC_LINK);
      } else if (stat.isDirectory()) {
        write32(buf+16, WASI_FILETYPE_DIRECTORY);
      } else if (stat.isCharDevice()) {
        write32(buf+16, WASI_FILETYPE_CHARACTER_DEVICE);
      } else if (stat.isBlockDevice()) {
        write32(buf+16, WASI_FILETYPE_BLOCK_DEVICE);
      } else {
        write32(buf+16, WASI_FILETYPE_UNKNOWN);
      }
      return WASI_ESUCCESS;
    },
    path_open: function(dirfd, dirflags, path, path_len, oflags, fs_rights_base, fs_rights_inheriting, fs_flags, fd_out) {
      trace('path_open', arguments);
      checkHeap();
      let filename = readStr(path, path_len);
      trace('path_open', ['dirfd=' + dirfd, 'path=' + filename, 'flags=' + oflags]);
      if (!isValidFD(dirfd))
        return WASI_EBADF;
      let file = openFiles[dirfd];
      if (file != rootdir)
        return WASI_EBADF;
      // TODO(sbc): Implement open flags (e.g. O_CREAT)
      if (oflags)
        return WASI_ENOTSUP;
      if (fs_flags)
        return WASI_ENOTSUP;
      let fd = nextFD;
      filename = file.rootdir + filename;
      openFiles[fd] = openFile(filename);
      write32(fd_out, fd);
      while (openFiles[nextFD] != undefined)
        nextFD++;
      return WASI_ESUCCESS;
    },
    path_unlink_file: function(dirfd, path, path_len) {
      checkHeap();
      let filename = readStr(path, path_len);
      trace('path_unlink_file', ['dirfd=' + dirfd, 'path=' + filename]);
      let file = openFiles[dirfd];
      if (file != rootdir)
        return WASI_EBADF;
      filename = file.rootdir + filename;
      trace('path_unlink_file', ['path=' + filename]);
      //fs.unlinkSync(filename);
      return WASI_ENOTSUP;
    },
    path_remove_directory: function(dirfd, path, path_len) {
      trace('path_remove_directory', ['dirfd=' + dirfd, 'path=' + readStr(path, path_len)]);
      throw new NotYetImplementedException('path_remove_directory');
    },
    random_get: function(buf, buf_len) {
      trace('random_get', arguments);
      return WASI_ESUCCESS;
    }
  }

  return {
    onExit: function() {
      for (let k in openFiles){
        if (openFiles.hasOwnProperty(k)) {
          openFiles[k].flush();
        }
      }
    },
    setArgv: function(new_argv) {
      argv = new_argv;
    },
    api: module_api
  };
})();

let ffi = (function() {
  let env = {
    memory: default_memory,
    // Any non-wasi dependencies end up under 'env'.
    // TODO(sbc): Implement on the wasm side or add to WASI?
    _Unwind_RaiseException: function() {
      throw new NotYetImplementedException('_Unwind_RaiseException');
    }
  }
  return {
    env: env,
    wasi_snapshot_preview1: wasi_interface.api
  };
})();

if (arguments.length < 1)
  throw new Error('Expected at least one wasm module to load.');

function loadWasm(file_path) {
  const buf = (typeof readbuffer === 'function')
    ? new Uint8Array(readbuffer(file_path))
    : read(file_path, 'binary');
  let instance = new WebAssembly.Instance(new WebAssembly.Module(buf), ffi)
  if (instance.exports.memory) {
    setHeap(instance.exports.memory);
  } else {
    setHeap(default_memory)
  }
  return instance;
}

let main_module_name = arguments[0];
wasi_interface.setArgv(arguments)

main_module = loadWasm(main_module_name);

if (!(main_module.exports._start instanceof Function))
  throw new Error('_start not found');

try {
  main_module.exports._start();
  wasi_interface.onExit();
  print(main_module_name + '::_start returned normally');
} catch (e) {
  wasi_interface.onExit();
  if (e instanceof TerminateWasmException) {
    print('Program terminated with: ' + e.exit_code);
    quit(e.exit_code);
  } else if (e instanceof NotYetImplementedException) {
    print('NotYetImplemented: ' + e.what);
  } else if (e instanceof WebAssembly.RuntimeError) {
    print('Runtime trap: ' + e.message);
  } else {
    print('Unknown exception of type `' + typeof(e) + '`: ' + e);
  }
  throw e;
}
