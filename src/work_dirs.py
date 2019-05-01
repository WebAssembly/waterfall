# -*- coding: utf-8 -*-

#   Copyright 2019 WebAssembly Community Group participants
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

import os


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WORK_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), 'src', 'work')

DEFAULT_SYNC_DIR = os.path.join(DEFAULT_WORK_DIR)
DEFAULT_BUILD_DIR = os.path.join(DEFAULT_WORK_DIR)
DEFAULT_PREBUILT_DIR = os.path.join(DEFAULT_WORK_DIR)
DEFAULT_TEST_DIR = os.path.join(DEFAULT_WORK_DIR)
DEFAULT_INSTALL_DIR = os.path.join(DEFAULT_WORK_DIR, 'wasm-install')

dirs = {}


def MakeGetterSetter(path_type, default):
  def getter():
    return dirs.get(path_type, default)

  def setter(dir):
    if path_type in dirs:
      raise Exception('Path %s set more than once' % path_type)
    dirs[path_type] = os.path.abspath(dir)

  return getter, setter


GetSync, SetSync = MakeGetterSetter('sync', DEFAULT_SYNC_DIR)
GetBuild, SetBuild = MakeGetterSetter('build', DEFAULT_BUILD_DIR)
GetPrebuilt, SetPrebuilt = MakeGetterSetter('prebuilt', DEFAULT_PREBUILT_DIR)
GetTest, SetTest = MakeGetterSetter('test', DEFAULT_TEST_DIR)
GetInstall, SetInstall = MakeGetterSetter('install', DEFAULT_INSTALL_DIR)


def GetAll():
  return [GetSync(), GetBuild(), GetTest(), GetInstall()]
