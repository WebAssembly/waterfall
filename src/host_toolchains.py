#! /usr/bin/env python
# -*- coding: utf-8 -*-

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

import json
import os

import proc

# Update 3 final with patches with 10.0.10586.0 SDK.
# Taken from https://cs.chromium.org/chromium/src/build/vs_toolchain.py?rcl=0&l=304
# and should periodically be updated as Chromium gets updated.
WIN_TOOLCHAIN_HASH = 'd5dc33b15d1b2c086f2f6632e2fd15882f80dbd3'
#PREBUILT_CLANG = os.path.join(WORK_DIR, 'chromium-clang')
#PREBUILT_CLANG_TOOLS_CLANG = os.path.join(PREBUILT_CLANG, 'tools', 'clang')
#PREBUILT_CLANG_BIN = os.path.join(
#    PREBUILT_CLANG, 'third_party', 'llvm-build', 'Release+Asserts', 'bin')
#CC = os.path.join(PREBUILT_CLANG_BIN, 'clang')
#CXX = os.path.join(PREBUILT_CLANG_BIN, 'clang++')


def SyncPrebuiltClang(name, src_dir, git_repo):
  tools_clang = os.path.join(src_dir, 'tools', 'clang')
  if os.path.isdir(tools_clang):
    print 'Prebuilt Chromium Clang directory already exists'
  else:
    print 'Cloning Prebuilt Chromium Clang directory'
    Mkdir(src_dir)
    Mkdir(os.path.join(src_dir, 'tools'))
    Git(['clone', git_repo, tools_clang])
  Git(['fetch'], cwd=tools_clang)
  proc.check_call(
      [os.path.join(tools_clang, 'scripts', 'update.py')])
  assert os.path.isfile(CC), 'Expect clang at %s' % CC
  assert os.path.isfile(CXX), 'Expect clang++ at %s' % CXX
  return ('chromium-clang', tools_clang)


def SyncWinToolchain(v8_src_dir):
  print v8_src_dir
  os.environ['GYP_MSVS_VERSION'] = '2015'
  proc.check_call([os.path.join(v8_src_dir, 'gypfiles', 'vs_toolchain.py'), 'update'])


def GetToolchainPath(cc):
  v8_src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'work', 'v8', 'v8')
  proc.check_call(
    [os.path.join(v8_src_dir, 'gypfiles', 'vs_toolchain.py'),
     'get_toolchain_dir'])
  
  with open(os.path.join(v8_src_dir, 'gypfiles', 'win_toolchain.json')) as f:
    paths = json.load(f)
  
  toolbin = os.path.join(paths['path'], 'VC', 'bin', 'amd64')
  return os.path.join(toolbin, 'cl.exe')
