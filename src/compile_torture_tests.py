#! /usr/bin/env python

#   Copyright 2015 WebAssembly Community Group participants
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import argparse
import fnmatch
import glob
import os
import os.path
import sys

import testing

# For debugging purposes set this to a source file name to test just a single
# file.
test_filter = None


def do_compile(infile, outfile, extras):
  """Create the command-line for a C compiler invocation."""
  if os.path.splitext(infile)[1] == '.C' or 'g++.dg' in infile:  # lol windows
    return [extras['cxx'], infile, '-o', outfile] + extras['cxxflags']
  else:
    return [extras['cc'], infile, '-o', outfile] + extras['cflags']


def create_outname(outdir, infile, extras):
  if os.path.splitext(infile)[1] == '.C':
    parts = infile.split(os.path.sep)
    parts = parts[parts.index('testsuite') + 2:]
    basename = '__'.join(parts)
  else:
    basename = os.path.basename(infile)
  rtn = os.path.join(outdir, basename + extras['suffix'])
  if os.path.exists(rtn):
    raise Exception("already exists: " + rtn)
  return rtn


def find_runnable_tests(directory, pattern):
  results = []
  for root, dirs, files in os.walk(directory):
    if os.path.basename(root) == 'ext':
      continue
    for filename in files:
      if fnmatch.fnmatch(filename, pattern):
        fullname = os.path.join(root, filename)
        with open(fullname, 'r') as f:
          header = f.read(1024)
        if '{ dg-do run }' in header and 'dg-additional-sources' not in header:
          results.append(fullname)
  return results


def run(cc, cxx, testsuite, sysroot_dir, fails, exclusions, out, config, opt):
  """Compile all torture tests."""
  script_dir = os.path.dirname(os.path.abspath(__file__))
  pre_js = os.path.join(script_dir, 'em_pre.js')

  cflags_common = ['-DSTACK_SIZE=524288',
                   '-w', '-Wno-implicit-function-declaration', '-' + opt]
  cflags_c = ['--std=gnu89']
  cflags_cxx = []
  cflags_extra = {
      'clang': ['-c', '--sysroot=%s' % sysroot_dir],
      'emscripten': ['--pre-js', pre_js],
  }
  suffix = {
      'clang': '.o',
      'emscripten': '.js',
  }[config]

  assert os.path.isdir(out), 'Cannot find outdir %s' % out
  assert os.path.isfile(cc), 'Cannot find C compiler at %s' % cc
  assert os.path.isfile(cxx), 'Cannot find C++ compiler at %s' % cxx
  assert os.path.isdir(testsuite), 'Cannot find testsuite at %s' % testsuite

  # Currently we build the following parts of the gcc test suite:
  #  - testsuite/gcc.c-torture/execute/*.c
  #  - testsuite/g++.dg (all executable tests)
  # TODO(sbc) Also more parts of the test suite
  c_torture = os.path.join(testsuite, 'gcc.c-torture', 'execute')
  assert os.path.isdir(c_torture), ('Cannot find C tests at %s' % c_torture)
  test_files = glob.glob(os.path.join(c_torture, '*.c'))

  if config == 'clang':
    # Only build the C++ tests when linking with lld
    cxx_test_dir = os.path.join(testsuite, 'g++.dg')
    assert os.path.isdir(cxx_test_dir), ('Cannot find C++ tests at %s' %
                                         cxx_test_dir)
    test_files += find_runnable_tests(cxx_test_dir, '*.[Cc]')

  cflags = cflags_common + cflags_c + cflags_extra[config]
  cxxflags = cflags_common + cflags_cxx + cflags_extra[config]

  if test_filter:
    test_files = fnmatch.filter(test_files, test_filter)

  result = testing.execute(
      tester=testing.Tester(
          command_ctor=do_compile,
          outname_ctor=create_outname,
          outdir=out,
          extras={'cc': cc, 'cxx': cxx, 'cflags': cflags,
                  'cxxflags': cxxflags, 'suffix': suffix}),
      inputs=test_files,
      fails=fails,
      exclusions=exclusions,
      attributes=[config, opt])

  return result


def main():
  parser = argparse.ArgumentParser(description='Compile GCC torture tests.')
  parser.add_argument('--cc', type=str, required=True,
                      help='C compiler path')
  parser.add_argument('--cxx', type=str, required=True,
                      help='C++ compiler path')
  parser.add_argument('--testsuite', type=str, required=True,
                      help='GCC testsuite tests path')
  parser.add_argument('--sysroot', type=str, required=True,
                      help='Sysroot directory')
  parser.add_argument('--fails', type=str, required=True,
                      help='Expected failures')
  parser.add_argument('--out', type=str, required=True,
                      help='Output directory')
  parser.add_argument('--config', type=str, required=True,
                      help='configuration to use')
  args = parser.parse_args()
  return run(cc=args.cc,
             cxx=args.cxx,
             testsuite=args.testsuite,
             sysroot_dir=args.sysroot,
             fails=args.fails,
             out=args.out,
             config=args.config)


if __name__ == '__main__':
  sys.exit(main())
