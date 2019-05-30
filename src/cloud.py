#! /usr/bin/env python

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

import proc
from buildbot import IsEmscriptenReleasesBot, IsUploadingBot

CLOUD_STORAGE_BASE_URL = 'https://storage.googleapis.com/'
WATERFALL_CLOUD_STORAGE_PATH = 'wasm-llvm/builds/'
EMSCRIPTEN_RELEASES_CLOUD_STORAGE_PATH = \
    'webassembly/emscripten-releases-builds/'


def GetCloudStoragePath():
  if IsEmscriptenReleasesBot():
    return EMSCRIPTEN_RELEASES_CLOUD_STORAGE_PATH
  else:
    return WATERFALL_CLOUD_STORAGE_PATH


def Upload(local, remote):
  """Upload file to Cloud Storage."""
  if not IsUploadingBot():
    return
  remote = GetCloudStoragePath() + remote
  proc.check_call(
      ['gsutil.py', 'cp', local, 'gs://' + remote])
  return CLOUD_STORAGE_BASE_URL + remote


def Download(remote, local):
  remote = GetCloudStoragePath() + remote
  proc.check_call(['gsutil.py', 'cp', 'gs://' + remote, local])
