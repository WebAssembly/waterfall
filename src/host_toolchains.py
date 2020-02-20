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

import glob
import json
import os
import shutil

import file_util
import proc
import work_dirs


force_host_clang = True


def SetupToolchain():
  return ['vpython.bat',
          os.path.join(work_dirs.GetV8(), 'build', 'toolchain',
                       'win', 'setup_toolchain.py')]


def VSToolchainPy():
  return ['vpython.bat',
          os.path.join(work_dirs.GetV8(), 'build', 'vs_toolchain.py')]


def WinToolchainJson():
  return os.path.join(work_dirs.GetV8(), 'build', 'win_toolchain.json')


def SyncPrebuiltClang(name, src_dir):
  """Update the prebuilt clang toolchain used by chromium bots"""
  tools_clang = os.path.join(src_dir, 'tools', 'clang')
  assert os.path.isdir(tools_clang)
  proc.check_call(
      [os.path.join(tools_clang, 'scripts', 'update.py')])


def SyncWinToolchain():
  """Update the VS toolchain used by Chromium bots"""
  proc.check_call(VSToolchainPy() + ['update'])


def GetVSEnv(dir):
  """Return the configured VS build environment block as a python dict."""
  # The format is a list of nul-terminated strings of the form var=val
  # where 'var' is the environment variable name, and 'val' is its value
  env = os.environ.copy()
  with open(os.path.join(dir, 'environment.x64'), 'rb') as f:
    entries = f.read().decode().split('\0')
    for e in entries:
      if not e:
        continue
      var, val = e.split('=', 1)
      env[var] = val
      print('ENV: %s = %s' % (var, val))

  return env


def GetRuntimeDir():
  # Get the chromium-packaged toolchain directory info in a JSON file
  proc.check_call(VSToolchainPy() + ['get_toolchain_dir'])
  with open(WinToolchainJson()) as f:
    paths = json.load(f)
  # Extract the 64-bit runtime path
  return [path for path in paths['runtime_dirs'] if path.endswith('64')][0]


def SetUpVSEnv(outdir):
  """Set up the VS build environment used by Chromium bots"""

  # Get the chromium-packaged toolchain directory info in a JSON file
  proc.check_call(VSToolchainPy() + ['get_toolchain_dir'])
  with open(WinToolchainJson()) as f:
    paths = json.load(f)

  # Write path information (usable by a non-chromium build) into an environment
  # block
  runtime_dirs = os.pathsep.join(paths['runtime_dirs'])
  proc.check_call(SetupToolchain() +
                  ['foo', paths['win_sdk'], runtime_dirs,
                   'win', 'x64', 'environment.x64'],
                  cwd=outdir)
  return GetVSEnv(outdir)


def CopyDlls(dir, configuration):
  """Copy MSVS Runtime dlls into a build directory"""
  file_util.Mkdir(dir)
  proc.check_call(VSToolchainPy() + ['copy_dlls', dir, configuration, 'x64'])
  # LLD needs also concrt140.dll, which the Chromium copy_dlls doesn't include.
  for dll in glob.glob(os.path.join(GetRuntimeDir(), 'concrt140*.dll')):
    print('Copying %s to %s' % (dll, dir))
    shutil.copy2(dll, dir)


def UsingGoma():
  return 'GOMA_DIR' in os.environ


def GomaDir():
  return os.environ['GOMA_DIR']


def CMakeLauncherFlags():
  flags = []
  if UsingGoma():
    compiler_launcher = os.path.join(GomaDir(), 'gomacc')
  else:
    try:
      compiler_launcher = proc.Which('ccache')
    except: # noqa
      return flags

    if ShouldForceHostClang():
      # This flag is only present in clang.
      flags.extend(['-DCMAKE_%s_FLAGS=-Qunused-arguments' %
                    c for c in ['C', 'CXX']])

  flags.extend(['-DCMAKE_%s_COMPILER_LAUNCHER=%s' %
                (c, compiler_launcher) for c in ['C', 'CXX']])
  return flags


def NinjaJobs():
  if UsingGoma() and force_host_clang:
    return ['-j', '50']
  return []


def SetForceHostClang(force):
  global force_host_clang
  force_host_clang = force


def ShouldForceHostClang():
  return force_host_clang
