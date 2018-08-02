#! /usr/bin/env python
# -*- coding: utf-8 -*-

#   Copyright 2016 WebAssembly Community Group participants
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

import file_util
import proc

WORK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'work')
CR_BUILD_DIR = os.path.join(WORK_DIR, 'build')
SETUP_TOOLCHAIN = os.path.join(CR_BUILD_DIR, 'toolchain', 'win',
                               'setup_toolchain.py')
V8_SRC_DIR = os.path.join(WORK_DIR, 'v8', 'v8')
VS_TOOLCHAIN = os.path.join(V8_SRC_DIR, 'build', 'vs_toolchain.py')
WIN_TOOLCHAIN_JSON = os.path.join(V8_SRC_DIR, 'build', 'win_toolchain.json')

# TODO(sbc): Remove this once upstream llvm is fixed rolled into chrome.
# See: https://bugs.llvm.org/show_bug.cgi?id=38165
PREBUILD_CLANG_REVISION = 'ebf0d4a36bb989c366e78a4c20564cd4656197e6'


def SyncPrebuiltClang(name, src_dir, git_repo):
  """Update the prebuilt clang toolchain used by chromium bots"""
  tools_clang = os.path.join(src_dir, 'tools', 'clang')
  if os.path.isdir(tools_clang):
    print 'Prebuilt Chromium Clang directory already exists'
  else:
    print 'Cloning Prebuilt Chromium Clang directory'
    file_util.Mkdir(src_dir)
    file_util.Mkdir(os.path.join(src_dir, 'tools'))
    proc.check_call(['git', 'clone', git_repo, tools_clang])
  proc.check_call(['git', 'fetch'], cwd=tools_clang)
  proc.check_call(
      ['git', 'checkout', PREBUILD_CLANG_REVISION], cwd=tools_clang)
  proc.check_call(
      [os.path.join(tools_clang, 'scripts', 'update.py')])
  return ('chromium-clang', tools_clang)


def SyncWinToolchain():
  """Update the VS toolchain used by Chromium bots"""
  proc.check_call([VS_TOOLCHAIN, 'update'])


def GetVSEnv(dir):
  """Return the configured VS build environment block as a python dict."""
  # The format is a list of nul-terminated strings of the form var=val
  # where 'var' is the environment variable name, and 'val' is its value
  env = os.environ.copy()
  with open(os.path.join(dir, 'environment.x64'), 'rb') as f:
    entries = f.read().split('\0')
    for e in entries:
      if not e:
        continue
      var, val = e.split('=', 1)
      env[var] = val

  return env


def SetUpVSEnv(outdir):
  """Set up the VS build environment used by Chromium bots"""

  # Get the chromium-packaged toolchain directory info in a JSON file
  proc.check_call([VS_TOOLCHAIN, 'get_toolchain_dir'])
  with open(WIN_TOOLCHAIN_JSON) as f:
    paths = json.load(f)

  # Write path information (usable by a non-chromium build) into an environment
  # block
  runtime_dirs = os.pathsep.join(paths['runtime_dirs'])
  proc.check_call([SETUP_TOOLCHAIN,
                   'foo', paths['win_sdk'], runtime_dirs,
                   'win', 'x64', 'environment.x64'],
                  cwd=outdir)
  return GetVSEnv(outdir)


def CopyDlls(dir, configuration):
  """Copy MSVS Runtime dlls into a build directory"""
  proc.check_call([VS_TOOLCHAIN, 'copy_dlls', dir, configuration, 'x64'])


def UsingGoma():
  return 'GOMA_DIR' in os.environ


def GomaDir():
  return os.environ['GOMA_DIR']


def CmakeLauncherFlags():
  flags = []
  if UsingGoma():
    compiler_launcher = os.path.join(GomaDir(), 'gomacc')
  else:
    try:
      compiler_launcher = proc.Which('ccache', WORK_DIR)
      flags.extend(['-DCMAKE_%s_FLAGS=-Qunused-arguments' %
                    c for c in ['C', 'CXX']])
    except:
      compiler_launcher = None

  if compiler_launcher:
    flags.extend(['-DCMAKE_%s_COMPILER_LAUNCHER=%s' %
                  (c, compiler_launcher) for c in ['C', 'CXX']])
  return flags


def NinjaJobs():
  if UsingGoma():
    return ['-j', '50']
  return []
