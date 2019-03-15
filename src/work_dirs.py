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
# Root of the waterfall git repo
ROOT_DIR = os.path.dirname(SCRIPT_DIR)

DEFAULT_SYNC_DIR = os.path.join(ROOT_DIR, 'sync')
DEFAULT_BUILD_DIR = os.path.join(ROOT_DIR, 'build')
DEFAULT_TEST_DIR = os.path.join(ROOT_DIR, 'test-out')
DEFAULT_INSTALL_DIR = os.path.join(ROOT_DIR, 'install')

dirs = {}


def set_path(path_type, dir):
  global dirs
  if path_type in dirs:
    raise Exception('Path %s set more than once' % path_type)
  dirs[path_type] = dir


def GetBuild():
  return dirs.get('build', DEFAULT_BUILD_DIR)


def SetBuild(dir):
  set_path('build', dir)
