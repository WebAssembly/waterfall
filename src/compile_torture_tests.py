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

import glob
import os
import os.path
import sys

import testing


CFLAGS = ['--std=gnu89', '--target=wasm32-unknown-unknown', '-S', '-O2',
          '-DSTACK_SIZE=1044480',
          '-w', '-Wno-implicit-function-declaration']


def create_outname(outdir, infile):
  """Create the output file's name."""
  basename = os.path.basename(infile)
  outname = basename + '.s'
  return os.path.join(outdir, outname)


def c_compile(infile, outfile, extras):
  """Create the command-line for a C compiler invocation."""
  return [extras['c'], infile, '-o', outfile] + CFLAGS


def run(c, cxx, testsuite, fails, out):
  """Compile all torture tests."""
  assert os.path.isfile(c), 'Cannot find C compiler at %s' % c
  assert os.path.isfile(cxx), 'Cannot find C++ compiler at %s' % cxx
  assert os.path.isdir(testsuite), 'Cannot find testsuite at %s' % testsuite
  # TODO(jfb) Also compile other C tests, as well as C++ tests under g++.dg.
  c_torture = os.path.join(testsuite, 'gcc.c-torture', 'execute')
  assert os.path.isdir(c_torture), ('Cannot find C torture tests at %s' %
                                    c_torture)
  assert os.path.isdir(out), 'Cannot find outdir %s' % out
  c_test_files = glob.glob(os.path.join(c_torture, '*c'))
  return testing.execute(
      tester=testing.Tester(
          command_ctor=c_compile,
          outname_ctor=create_outname,
          outdir=out,
          extras={'c': c}),
      inputs=c_test_files,
      fails=fails)


def getargs():
  import argparse
  parser = argparse.ArgumentParser(description='Compile GCC torture tests.')
  parser.add_argument('--c', type=str, required=True,
                      help='C compiler path')
  parser.add_argument('--cxx', type=str, required=True,
                      help='C++ compiler path')
  parser.add_argument('--testsuite', type=str, required=True,
                      help='GCC testsuite tests path')
  parser.add_argument('--fails', type=str, required=True,
                      help='Expected failures')
  parser.add_argument('--out', type=str, required=True,
                      help='Output directory')
  return parser.parse_args()


if __name__ == '__main__':
  args = getargs()
  sys.exit(run(args.c, args.cxx, args.testsuite, args.fails, args.out))
