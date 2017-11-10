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

import argparse
import glob
import json
import multiprocessing
import os
import shutil
import sys
import tarfile
import tempfile
import textwrap
import time
import traceback
import urllib2
import zipfile

import assemble_files
import buildbot
import cloud
import compile_torture_tests
import execute_files
from file_util import Chdir, CopyTree, Mkdir, Remove
import host_toolchains
import link_assembly_files
import proc


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.path.join(SCRIPT_DIR, 'work')

LLVM_SRC_DIR = os.path.join(WORK_DIR, 'llvm')
CLANG_SRC_DIR = os.path.join(LLVM_SRC_DIR, 'tools', 'clang')
LLD_SRC_DIR = os.path.join(LLVM_SRC_DIR, 'tools', 'lld')
COMPILER_RT_SRC_DIR = os.path.join(WORK_DIR, 'compiler-rt')
LLVM_TEST_SUITE_SRC_DIR = os.path.join(WORK_DIR, 'llvm-test-suite')

EMSCRIPTEN_SRC_DIR = os.path.join(WORK_DIR, 'emscripten')
FASTCOMP_SRC_DIR = os.path.join(WORK_DIR, 'emscripten-fastcomp')

GCC_SRC_DIR = os.path.join(WORK_DIR, 'gcc')
GCC_TEST_DIR = os.path.join(GCC_SRC_DIR, 'gcc', 'testsuite')

V8_SRC_DIR = os.path.join(WORK_DIR, 'v8', 'v8')
JSC_SRC_DIR = os.path.join(WORK_DIR, 'jsc')
WABT_SRC_DIR = os.path.join(WORK_DIR, 'wabt')

OCAML_DIR = os.path.join(WORK_DIR, 'ocaml')  # OCaml always does in-tree build
OCAMLBUILD_DIR = os.path.join(WORK_DIR, 'ocamlbuild')

SPEC_SRC_DIR = os.path.join(WORK_DIR, 'spec')
ML_DIR = os.path.join(SPEC_SRC_DIR, 'interpreter')
BINARYEN_SRC_DIR = os.path.join(WORK_DIR, 'binaryen')
MUSL_SRC_DIR = os.path.join(WORK_DIR, 'musl')

FIND_SVN_REV = os.path.join(SCRIPT_DIR, 'find_svn_rev.py')

PREBUILT_CLANG = os.path.join(WORK_DIR, 'chromium-clang')
PREBUILT_CLANG_TOOLS_CLANG = os.path.join(PREBUILT_CLANG, 'tools', 'clang')
PREBUILT_CLANG_BIN = os.path.join(
    PREBUILT_CLANG, 'third_party', 'llvm-build', 'Release+Asserts', 'bin')
CC = os.path.join(PREBUILT_CLANG_BIN, 'clang')
CXX = os.path.join(PREBUILT_CLANG_BIN, 'clang++')

LLVM_OUT_DIR = os.path.join(WORK_DIR, 'llvm-out')
V8_OUT_DIR = os.path.join(V8_SRC_DIR, 'out.gn', 'x64.release')
JSC_OUT_DIR = os.path.join(JSC_SRC_DIR, 'current-release')
WABT_OUT_DIR = os.path.join(WORK_DIR, 'wabt-out')
OCAML_OUT_DIR = os.path.join(WORK_DIR, 'ocaml-out')
BINARYEN_OUT_DIR = os.path.join(WORK_DIR, 'binaryen-out')
FASTCOMP_OUT_DIR = os.path.join(WORK_DIR, 'fastcomp-out')
MUSL_OUT_DIR = os.path.join(WORK_DIR, 'musl-out')
COMPILER_RT_OUT_DIR = os.path.join(WORK_DIR, 'compiler-rt-out')
TORTURE_S_OUT_DIR = os.path.join(WORK_DIR, 'torture-s')
TORTURE_O_OUT_DIR = os.path.join(WORK_DIR, 'torture-o')
ASM2WASM_TORTURE_OUT_DIR = os.path.join(WORK_DIR, 'asm2wasm-torture-out')
EMSCRIPTENWASM_TORTURE_OUT_DIR = os.path.join(WORK_DIR, 'emwasm-torture-out')
EMSCRIPTEN_TEST_OUT_DIR = os.path.join(WORK_DIR, 'emtest-out')
EMSCRIPTEN_ASMJS_TEST_OUT_DIR = os.path.join(WORK_DIR, 'emtest-asm2wasm-out')

INSTALL_DIR = os.path.join(WORK_DIR, 'wasm-install')
INSTALL_BIN = os.path.join(INSTALL_DIR, 'bin')
INSTALL_LIB = os.path.join(INSTALL_DIR, 'lib')
INSTALL_SYSROOT = os.path.join(INSTALL_DIR, 'sysroot')

EMSCRIPTEN_CONFIG_ASMJS = os.path.join(INSTALL_DIR, 'emscripten_config')
EMSCRIPTEN_CONFIG_WASM = os.path.join(INSTALL_DIR, 'emscripten_config_vanilla')

# Avoid flakes: use cached repositories to avoid relying on external network.
GITHUB_REMOTE = 'github'
GITHUB_SSH = 'git@github.com:'
GIT_MIRROR_BASE = 'https://chromium.googlesource.com/'
LLVM_MIRROR_BASE = 'https://llvm.googlesource.com/'
GITHUB_MIRROR_BASE = GIT_MIRROR_BASE + 'external/github.com/'
WASM_GIT_BASE = GITHUB_MIRROR_BASE + 'WebAssembly/'
EMSCRIPTEN_GIT_BASE = GITHUB_MIRROR_BASE + 'kripken/'
MUSL_GIT_BASE = 'https://github.com/jfbastien/'
WEBKIT_GIT_BASE = 'https://github.com/WebKit/'
OCAML_GIT_BASE = 'https://github.com/ocaml/'

# TODO(sbc): Remove this once lld changes are upstream
LLD_GIT_BASE = 'https://github.com/WebAssembly/'
LLD_BRANCH = 'wasm'

# Name of remote for build script to use. Don't touch origin to avoid
# clobbering any local development.
WATERFALL_REMOTE = '_waterfall'

WASM_STORAGE_BASE = 'https://wasm.storage.googleapis.com/'

# These versions are the git tags to check out.
OCAML_VERSION = '4.05.0'
OCAMLBUILD_VERSION = '0.11.0'
OCAML_BIN_DIR = os.path.join(OCAML_OUT_DIR, 'bin')

GNUWIN32_DIR = os.path.join(WORK_DIR, 'gnuwin32')
GNUWIN32_ZIP = 'gnuwin32.zip'

options = None


def IsWindows():
  return sys.platform == 'win32'


def IsLinux():
  return sys.platform == 'linux2'


def IsMac():
  return sys.platform == 'darwin'


def Executable(name, extension='.exe'):
  return name + extension if IsWindows() else name


def WindowsFSEscape(path):
  return os.path.normpath(path).replace('\\', '/')


def NodePlatformName():
  return {'darwin': 'darwin-x64',
          'linux2': 'linux-x64',
          'win32': 'win32'}[sys.platform]


def CMakePlatformName():
  return {'linux2': 'Linux',
          'darwin': 'Darwin',
          'win32': 'win32'}[sys.platform]


def CMakeArch():
  return 'x86' if IsWindows() else 'x86_64'


def CMakeBinDir():
  if IsMac():
    return os.path.join('CMake.app', 'Contents', 'bin')
  else:
    return 'bin'


# Use prebuilt Node.js because the buildbots don't have node preinstalled
NODE_VERSION = '7.0.0'
NODE_BASE_NAME = 'node-v' + NODE_VERSION + '-'

PREBUILT_CMAKE_VERSION = '3.4.3'
PREBUILT_CMAKE_BASE_NAME = 'cmake-%s-%s-%s' % (PREBUILT_CMAKE_VERSION,
                                               CMakePlatformName(),
                                               CMakeArch())
PREBUILT_CMAKE_DIR = os.path.join(WORK_DIR, PREBUILT_CMAKE_BASE_NAME)
PREBUILT_CMAKE_BIN = os.path.join(PREBUILT_CMAKE_DIR, CMakeBinDir(), 'cmake')

NODE_BIN = Executable(os.path.join(WORK_DIR,
                                   NODE_BASE_NAME + NodePlatformName(),
                                   'bin', 'node'))

# Known failures.
IT_IS_KNOWN = 'known_gcc_test_failures.txt'
LLVM_KNOWN_TORTURE_FAILURES = [os.path.join(LLVM_SRC_DIR, 'lib', 'Target',
                                            'WebAssembly', IT_IS_KNOWN)]
ASM2WASM_KNOWN_TORTURE_COMPILE_FAILURES = [os.path.join(
    SCRIPT_DIR, 'test', 'asm2wasm_compile_' + IT_IS_KNOWN)]
EMSCRIPTENWASM_KNOWN_TORTURE_COMPILE_FAILURES = [os.path.join(
    SCRIPT_DIR, 'test', 'emwasm_compile_' + IT_IS_KNOWN)]

RUN_KNOWN_TORTURE_FAILURES = [os.path.join(SCRIPT_DIR, 'test',
                                           'run_' + IT_IS_KNOWN)]
WAT2WASM_KNOWN_TORTURE_FAILURES = [os.path.join(SCRIPT_DIR, 'test',
                                                'wat2wasm_' + IT_IS_KNOWN)]
SPEC_KNOWN_TORTURE_FAILURES = [os.path.join(SCRIPT_DIR, 'test',
                                            'spec_' + IT_IS_KNOWN)]
S2WASM_KNOWN_TORTURE_FAILURES = [os.path.join(BINARYEN_SRC_DIR, 'test',
                                              's2wasm_' + IT_IS_KNOWN)]
LLD_KNOWN_TORTURE_FAILURES = [os.path.join(SCRIPT_DIR, 'test',
                              'lld_' + IT_IS_KNOWN)]
BINARYEN_SHELL_KNOWN_TORTURE_FAILURES = [
    os.path.join(BINARYEN_SRC_DIR, 'test',
                 's2wasm_known_binaryen_shell_test_failures.txt')]

# Optimization levels
BARE_TEST_OPT_FLAGS = ['O0', 'O2']
EMSCRIPTEN_TEST_OPT_FLAGS = ['O0', 'O3']


NPROC = multiprocessing.cpu_count()

# Schedulers which can kick off new builds, from:
# https://chromium.googlesource.com/chromium/tools/build/+/master/masters/master.client.wasm.llvm/builders.pyl
SCHEDULERS = {
    None: 'forced',
    'None': 'forced',
    'llvm_commits': 'llvm',
    'clang_commits': 'clang'
}

# Buildbot-provided environment.
BUILDBOT_SCHEDULER = os.environ.get('BUILDBOT_SCHEDULER', None)
SCHEDULER = SCHEDULERS[BUILDBOT_SCHEDULER]
BUILDBOT_REVISION = os.environ.get('BUILDBOT_REVISION', None)
BUILDBOT_BUILDNUMBER = os.environ.get('BUILDBOT_BUILDNUMBER', None)
BUILDBOT_BUILDERNAME = os.environ.get('BUILDBOT_BUILDERNAME', None)


# Pin the GCC revision so that new torture tests don't break the bot. This
# should be manually updated when convenient.
GCC_REVISION = 'b6125c702850488ac3bfb1079ae5c9db89989406'
GCC_CLONE_DEPTH = 1000


def CopyBinaryToArchive(binary, prefix=''):
  """All binaries are archived in the same tar file."""
  install_bin = os.path.join(INSTALL_DIR, prefix, 'bin')
  print 'Copying binary %s to archive %s' % (binary, install_bin)
  Mkdir(install_bin)
  shutil.copy2(binary, install_bin)


def CopyLibraryToArchive(library, prefix=''):
  """All libraries are archived in the same tar file."""
  install_lib = os.path.join(INSTALL_DIR, prefix, 'lib')
  print 'Copying library %s to archive %s' % (library, install_lib)
  Mkdir(install_lib)
  shutil.copy2(library, install_lib)


def CopyLibraryToSysroot(library):
  """All libraries are archived in the same tar file."""
  install_lib = os.path.join(INSTALL_SYSROOT, 'lib')
  print 'Copying library %s to archive %s' % (library, install_lib)
  Mkdir(install_lib)
  shutil.copy2(library, install_lib)


def Archive(directory, print_content=False):
  """Create an archive file from directory."""
  # Use the format "native" to the platform
  if not IsBuildbot():
    return
  if IsWindows():
    return Zip(directory, print_content)
  return Tar(directory, print_content)


def Tar(directory, print_content=False):
  assert os.path.isdir(directory), 'Must tar a directory to avoid tarbombs'
  (up_directory, basename) = os.path.split(directory)
  tar = os.path.join(up_directory, basename + '.tbz2')
  Remove(tar)
  if print_content:
    proc.check_call(['find', basename, '-type', 'f',
                     '-exec', 'ls', '-lhS', '{}', '+'], cwd=up_directory)
  proc.check_call(['tar', 'cjf', tar, basename], cwd=up_directory)
  proc.check_call(['ls', '-lh', tar], cwd=up_directory)
  return tar


def Zip(directory, print_content=False):
  assert os.path.isdir(directory), 'Must be a directory'
  dirname, basename = os.path.split(directory)
  archive = os.path.join(dirname, basename + '.zip')
  print 'Creating zip archive', archive
  with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(directory):
      for name in files:
        fs_path = os.path.join(root, name)
        zip_path = os.path.relpath(fs_path, os.path.dirname(directory))
        if print_content:
          print 'Adding', fs_path
        z.write(fs_path, zip_path)
  print 'Size:', os.stat(archive).st_size
  return archive


def UploadFile(local_name, remote_name):
  """Archive the file with the given name, and with the LLVM git hash."""
  if not IsBuildbot():
    return
  buildbot.Link('download', cloud.Upload(local_name, '%s/%s/%s' % (
      BUILDBOT_BUILDERNAME, BUILDBOT_BUILDNUMBER, remote_name)))


def UploadArchive(name, archive):
  """Archive the tar/zip file with the given name and the build number."""
  if not IsBuildbot():
    return
  extension = os.path.splitext(archive)[1]
  UploadFile(archive, 'wasm-%s%s' % (name, extension))


# Repo and subproject utilities

def GitRemoteUrl(cwd, remote):
  """Get the URL of a remote."""
  return proc.check_output(
      ['git', 'config', '--get', 'remote.%s.url' % remote], cwd=cwd).strip()


def HasRemote(cwd, remote):
  """"Checked whether the named remote exists."""
  remotes = proc.check_output(['git', 'remote'], cwd=cwd).strip().splitlines()
  return remote in remotes


def AddGithubRemote(cwd):
  """When using the cloned repository for development, it's useful to have a
  remote to github because origin points at a cache which is read-only."""
  remote_url = GitRemoteUrl(cwd, WATERFALL_REMOTE)
  if WASM_GIT_BASE not in remote_url:
    print '%s not a github mirror' % cwd
    return
  if HasRemote(cwd, GITHUB_REMOTE):
    print '%s has %s as its "%s" remote' % (
        cwd, GitRemoteUrl(cwd, GITHUB_REMOTE), GITHUB_REMOTE)
    return
  remote = GITHUB_SSH + '/'.join(remote_url.split('/')[-2:])
  print '%s has no github remote, adding %s' % (cwd, remote)
  proc.check_call(['git', 'remote', 'add', GITHUB_REMOTE, remote], cwd=cwd)


def GitConfigRebaseMaster(cwd):
  """Avoid generating a non-linear history in the clone

  The upstream repository is in Subversion. Use `git pull --rebase` instead of
  git pull: llvm.org/docs/GettingStarted.html#git-mirror
  """
  proc.check_call(['git', 'config', 'branch.master.rebase', 'true'], cwd=cwd)


def RemoteBranch(branch):
  """Get the remote-qualified branch name to use for waterfall"""
  return WATERFALL_REMOTE + '/' + branch


def IsBuildbot():
  """Return True if we are running on bot, False otherwise."""
  return BUILDBOT_BUILDNUMBER is not None


def GitUpdateRemote(src_dir, git_repo, remote_name):
  try:
    proc.check_call(
        ['git', 'remote', 'set-url', remote_name, git_repo], cwd=src_dir)
  except proc.CalledProcessError:
    # If proc.check_call fails it throws an exception. 'git remote set-url'
    # fails when the remote doesn't exist, so we should try to add it.
    proc.check_call(
        ['git', 'remote', 'add', remote_name, git_repo], cwd=src_dir)


class Source(object):
  """Metadata about a sync-able source repo on the waterfall"""
  def __init__(self, name, src_dir, git_repo,
               checkout=RemoteBranch('master'), depth=None,
               custom_sync=None, no_windows=False, no_linux=False):
    self.name = name
    self.src_dir = src_dir
    self.git_repo = git_repo
    self.checkout = checkout
    self.depth = depth
    self.custom_sync = custom_sync
    # Several of these steps have not been made to work on other platforms yet.
    # Temporarily disable them.
    self.no_windows = no_windows
    self.no_linux = no_linux

    # Ensure that git URLs end in .git.  We have had issues in the past where
    # github would not recognize the requests correctly otherwise due to
    # chromium's builders setting custom GIT_USER_AGENT:
    # https://bugs.chromium.org/p/chromium/issues/detail?id=711775
    if git_repo:
      assert git_repo.endswith('.git'), 'Git URLs should end in .git'

  def Sync(self, good_hashes=None):
    if IsWindows() and self.no_windows:
      print "Skipping %s: Doesn't work on Windows" % self.name
      return
    if IsLinux() and self.no_linux:
      print "Skipping %s: Doesn't work on Linux" % self.name
      return
    if good_hashes and good_hashes.get(self.name):
      self.checkout = good_hashes[self.name]
    if self.custom_sync:
      self.custom_sync(self.name, self.src_dir, self.git_repo)
    else:
      self.GitCloneFetchCheckout()

  def GitCloneFetchCheckout(self):
    """Clone a git repo if not already cloned, then fetch and checkout."""
    if os.path.isdir(self.src_dir):
      print '%s directory already exists' % self.name
    else:
      clone = ['clone', self.git_repo, self.src_dir]
      if self.depth:
        clone.append('--depth')
        clone.append(str(self.depth))
      proc.check_call(['git'] + clone)

    GitUpdateRemote(self.src_dir, self.git_repo, WATERFALL_REMOTE)
    proc.check_call(['git', 'fetch', '--tags', WATERFALL_REMOTE],
                    cwd=self.src_dir)
    if not self.checkout.startswith(WATERFALL_REMOTE + '/'):
      sys.stderr.write(('WARNING: `git checkout %s` not based on waterfall '
                        'remote (%s), checking out local branch'
                        % (self.checkout, WATERFALL_REMOTE)))
    proc.check_call(['git', 'checkout', self.checkout], cwd=self.src_dir)
    AddGithubRemote(self.src_dir)

  def CurrentGitInfo(self):
    if not os.path.exists(self.src_dir):
      return None

    def pretty(fmt):
      return proc.check_output(
          ['git', 'log', '-n1', '--pretty=format:%s' % fmt],
          cwd=self.src_dir).strip()
    try:
      remote = GitRemoteUrl(self.src_dir, WATERFALL_REMOTE)
    except proc.CalledProcessError:
      # Not all checkouts have the '_waterfall' remote (e.g. the waterfall
      # itself) so fall back to origin on failure
      remote = GitRemoteUrl(self.src_dir, 'origin')

    return {
        'hash': pretty('%H'),
        'name': pretty('%aN'),
        'email': pretty('%ae'),
        'subject': pretty('%s'),
        'remote': remote,
    }

  def PrintGitStatus(self):
    """"Print the current git status for the sync target."""
    print '<<<<<<<<<< STATUS FOR', self.name, '>>>>>>>>>>'
    if os.path.exists(self.src_dir):
      proc.check_call(['git', 'status'], cwd=self.src_dir)
    print


def ChromiumFetchSync(name, work_dir, git_repo,
                      checkout=RemoteBranch('master')):
  """Some Chromium projects want to use gclient for clone and dependencies."""
  if os.path.isdir(work_dir):
    print '%s directory already exists' % name
  else:
    # Create Chromium repositories one deeper, separating .gclient files.
    parent = os.path.split(work_dir)[0]
    Mkdir(parent)
    proc.check_call(['gclient', 'config', git_repo], cwd=parent)
    proc.check_call(['git', 'clone', git_repo], cwd=parent)

  GitUpdateRemote(work_dir, git_repo, WATERFALL_REMOTE)
  proc.check_call(['git', 'fetch', WATERFALL_REMOTE], cwd=work_dir)
  proc.check_call(['git', 'checkout', checkout], cwd=work_dir)
  proc.check_call(['gclient', 'sync'], cwd=work_dir)
  return (name, work_dir)


def SyncToolchain(name, src_dir, git_repo):
  if IsWindows():
    host_toolchains.SyncWinToolchain()
  else:
    host_toolchains.SyncPrebuiltClang(name, src_dir, git_repo)
    assert os.path.isfile(CC), 'Expect clang at %s' % CC
    assert os.path.isfile(CXX), 'Expect clang++ at %s' % CXX


def SyncArchive(out_dir, name, url):
  """Download and extract an archive (zip, tar.gz or tar.xz) file from a URL.

  The extraction happens in WORK_DIR and the convention for our archives is
  that they contain a top-level directory containing all the files; this
  is expected to be 'out_dir', so if 'out_dir' already exists then download
  will be skipped.
  """

  stamp_file = os.path.join(out_dir, 'stamp.txt')
  if os.path.isdir(out_dir):
    if os.path.isfile(stamp_file):
      with open(stamp_file) as f:
        stamp_url = f.read().strip()
      if stamp_url == url:
        print '%s directory already exists' % name
        return
    print '%s directory exists but is not up-to-date' % name
  print 'Downloading %s from %s' % (name, url)

  try:
    f = urllib2.urlopen(url)
    print 'URL: %s' % f.geturl()
    print 'Info: %s' % f.info()
    with tempfile.NamedTemporaryFile() as t:
      t.write(f.read())
      t.flush()
      t.seek(0)
      print 'Extracting...'
      ext = os.path.splitext(url)[-1]
      if ext == '.zip':
        with zipfile.ZipFile(t, 'r') as zip:
          zip.extractall(path=WORK_DIR)
      elif ext == '.xz':
        proc.check_call(['tar', '-xvf', t.name], cwd=WORK_DIR)
      else:
        tarfile.open(fileobj=t).extractall(path=WORK_DIR)
  except urllib2.URLError as e:
    print 'Error downloading %s: %s' % (url, e)
    raise

  with open(stamp_file, 'w') as f:
    f.write(url + '\n')


def SyncPrebuiltCMake(name, src_dir, git_repo):
  extension = '.zip' if IsWindows() else '.tar.gz'
  url = WASM_STORAGE_BASE + PREBUILT_CMAKE_BASE_NAME + extension
  SyncArchive(PREBUILT_CMAKE_DIR, 'cmake', url)


def SyncWindowsNode():
  if os.path.isfile(NODE_BIN):
    print NODE_BIN, 'already exists'
    return
  Mkdir(os.path.dirname(NODE_BIN))
  node_url = WASM_STORAGE_BASE + 'node.exe'
  print 'Downloading node.js %s from %s' % (NODE_VERSION, node_url)
  try:
    f = urllib2.urlopen(node_url)
    print 'URL: %s' % f.geturl()
    print 'Info: %s' % f.info()
    with open(NODE_BIN, 'wb') as n:
      n.write(f.read())
  except urllib2.URLError as e:
    print 'Error downloading %s: %s' % (node_url, e)
    raise
  return


def SyncPrebuiltNodeJS(name, src_dir, git_repo):
  if IsWindows():
    return SyncWindowsNode()
  extension = {'darwin': 'gz', 'linux2': 'xz'}[sys.platform]
  out_dir = os.path.join(WORK_DIR, NODE_BASE_NAME + NodePlatformName())
  tarball = NODE_BASE_NAME + NodePlatformName() + '.tar.' + extension
  node_url = WASM_STORAGE_BASE + tarball
  return SyncArchive(out_dir, name, node_url)


# Utilities needed for running LLVM regression tests on Windows
def SyncGNUWin32(name, src_dir, git_repo):
  if not IsWindows():
    return
  url = WASM_STORAGE_BASE + GNUWIN32_ZIP
  return SyncArchive(GNUWIN32_DIR, name, url)


def NoSync(*args):
  pass


ALL_SOURCES = [
    Source('waterfall', SCRIPT_DIR, None, custom_sync=NoSync),
    Source('llvm', LLVM_SRC_DIR,
           LLVM_MIRROR_BASE + 'llvm.git'),
    Source('clang', CLANG_SRC_DIR,
           LLVM_MIRROR_BASE + 'clang.git'),
    Source('compiler-rt', COMPILER_RT_SRC_DIR,
           LLVM_MIRROR_BASE + 'compiler-rt.git'),
    Source('llvm-test-suite', LLVM_TEST_SUITE_SRC_DIR,
           LLVM_MIRROR_BASE + 'test-suite.git'),
    Source('lld', LLD_SRC_DIR,
           LLD_GIT_BASE + 'lld.git',
           checkout=RemoteBranch(LLD_BRANCH)),
    Source('emscripten', EMSCRIPTEN_SRC_DIR,
           EMSCRIPTEN_GIT_BASE + 'emscripten.git',
           checkout=RemoteBranch('incoming')),
    Source('fastcomp', FASTCOMP_SRC_DIR,
           EMSCRIPTEN_GIT_BASE + 'emscripten-fastcomp.git',
           checkout=RemoteBranch('incoming')),
    Source('fastcomp-clang',
           os.path.join(FASTCOMP_SRC_DIR, 'tools', 'clang'),
           EMSCRIPTEN_GIT_BASE + 'emscripten-fastcomp-clang.git',
           checkout=RemoteBranch('incoming')),
    Source('gcc', GCC_SRC_DIR,
           GIT_MIRROR_BASE + 'chromiumos/third_party/gcc.git',
           checkout=GCC_REVISION, depth=GCC_CLONE_DEPTH),
    Source('v8', V8_SRC_DIR,
           GIT_MIRROR_BASE + 'v8/v8.git',
           custom_sync=ChromiumFetchSync),
    Source('jsc', JSC_SRC_DIR,
           WEBKIT_GIT_BASE + 'webkit.git', depth=1000,
           no_windows=True, no_linux=True),
    Source('host-toolchain', PREBUILT_CLANG,
           GIT_MIRROR_BASE + 'chromium/src/tools/clang.git',
           custom_sync=SyncToolchain),
    Source('cr-buildtools', os.path.join(WORK_DIR, 'build'),
           GIT_MIRROR_BASE + 'chromium/src/build.git'),
    Source('cmake', '', '',  # The source and git args are ignored.
           custom_sync=SyncPrebuiltCMake),
    Source('nodejs', '', '',  # The source and git args are ignored.
           custom_sync=SyncPrebuiltNodeJS),
    Source('gnuwin32', '', '',  # The source and git args are ignored.
           custom_sync=SyncGNUWin32),
    Source('wabt', WABT_SRC_DIR,
           WASM_GIT_BASE + 'wabt.git'),
    Source('spec', SPEC_SRC_DIR,
           WASM_GIT_BASE + 'spec.git', no_windows=True),
    Source('ocaml', OCAML_DIR,
           OCAML_GIT_BASE + 'ocaml.git',
           checkout='refs/tags/' + OCAML_VERSION, no_windows=True),
    Source('ocamlbuild', OCAMLBUILD_DIR,
           OCAML_GIT_BASE + 'ocamlbuild.git',
           checkout='refs/tags/' + OCAMLBUILD_VERSION, no_windows=True),
    Source('binaryen', BINARYEN_SRC_DIR,
           WASM_GIT_BASE + 'binaryen.git'),
    Source('musl', MUSL_SRC_DIR,
           MUSL_GIT_BASE + 'musl.git',
           checkout=RemoteBranch('wasm-prototype-1'))
]


def CurrentSvnRev(path):
  return int(proc.check_output(
      [FIND_SVN_REV, 'HEAD'], cwd=path).strip())


def FindPriorSvnRev(path, goal):
  revs = proc.check_output(
      ['git', 'rev-list', RemoteBranch('master')], cwd=path).splitlines()
  for rev in revs:
    num = proc.check_output(
        [FIND_SVN_REV, rev], cwd=path).strip()
    if int(num) <= goal:
      return rev
  raise Exception('Cannot find svn rev at or before %d' % goal)


def SyncToSvnRev(src_dir, svn_rev):
  """Sync git-svn-based repository to a given svn rev."""
  print 'Finding prior %s rev' % src_dir
  prior_rev = FindPriorSvnRev(src_dir, svn_rev)
  print 'Checking out %s rev: %s' % (src_dir, prior_rev)
  proc.check_call(['git', 'checkout', prior_rev], cwd=src_dir)


def SyncLLVMClang(good_hashes=None):
  def get_rev(rev_name):
    if good_hashes and good_hashes.get(rev_name):
      return good_hashes[rev_name]
    elif SCHEDULER == rev_name:
      return BUILDBOT_REVISION
    else:
      return RemoteBranch('master')

  proc.check_call(['git', 'checkout', get_rev('llvm')], cwd=LLVM_SRC_DIR)
  proc.check_call(['git', 'checkout', get_rev('clang')], cwd=CLANG_SRC_DIR)

  # If LLVM didn't trigger the new build then sync LLVM to the corresponding
  # clang revision, even if clang may not have triggered the build: usually
  # LLVM provides APIs which clang uses, which means that most synchronized
  # commits touch LLVM before clang. This should reduce the chance of breakage.
  primary = LLVM_SRC_DIR if SCHEDULER == 'llvm' else CLANG_SRC_DIR
  primary_svn_rev = CurrentSvnRev(primary)
  print 'SVN REV for %s: %d' % (primary, primary_svn_rev)
  # TODO(sbc): Add LLD_SRC_DIR to this list once LLD is upstream
  for srcdir in (LLVM_SRC_DIR, CLANG_SRC_DIR):
    if srcdir != primary:
      SyncToSvnRev(srcdir, primary_svn_rev)


def Clobber():
  if os.environ.get('BUILDBOT_CLOBBER'):
    buildbot.Step('Clobbering work dir')
    if os.path.isdir(WORK_DIR):
      Remove(WORK_DIR)


class Filter(object):
  """Filter for source or build rules, to allow including or excluding only
     selected targets.
  """
  def __init__(self, name=None, include=None, exclude=None):
    """
    include:
      if present, only items in it will be included (if empty, nothing will
      be included).
    exclude:
      if present, items in it will be excluded.
      include ane exclude cannot both be present.
    """
    if include and exclude:
      raise Exception('Filter cannot include both include and exclude rules')

    self.name = name
    self.include = include
    self.exclude = exclude

  def Apply(self, targets):
    """Return the filtered list of targets."""
    all_names = [t.name for t in targets]
    specified_names = self.include or self.exclude or []
    missing_names = [i for i in specified_names if i not in all_names]
    if missing_names:
      raise Exception('Invalid step name(s): {0}\n\n'
                      'Valid {1} steps:\n{2}'
                      .format(missing_names, self.name,
                              TextWrapNameList(prefix='', items=targets)))

    return [t for t in targets if self.Check(t.name)]

  def Check(self, target):
    """Return true if the specified target will be run."""
    if self.include is not None:
      return target in self.include

    if self.exclude is not None:
      return target not in self.exclude
    return True

  def All(self):
    """Return true if all possible targets will be run."""
    return self.include is None and not self.exclude

  def Any(self):
    """Return true if any targets can be run."""
    return self.include is None or len(self.include)


def SyncRepos(filter, sync_lkgr=False):
  if not filter.Any():
    return
  buildbot.Step('Sync Repos')

  good_hashes = None
  if sync_lkgr:
    if sys.platform.startswith('linux'):
      buildername = 'linux'
    elif sys.platform == 'darwin':
      buildername = 'mac'
    elif sys.platform == 'win32':
      buildername = 'windows'
    else:
      raise Exception('Unknown platform: %s' % sys.platform)
    lkgr_file = os.path.join(WORK_DIR, 'lkgr.json')
    cloud.Download('%s/lkgr.json' % buildername, lkgr_file)
    lkgr = json.loads(open(lkgr_file).read())
    good_hashes = {}
    for k, v in lkgr['repositories'].iteritems():
      good_hashes[k] = v.get('hash') if v else None

  for repo in filter.Apply(ALL_SOURCES):
    repo.Sync(good_hashes)
  # Special cases
  if filter.Check('clang') and not IsWindows():
    SyncLLVMClang(good_hashes)


def GetRepoInfo():
  """Collect a readable form of all repo information here, preventing the
  summary from getting out of sync with the actual list of repos."""
  info = {}
  for r in ALL_SOURCES:
    info[r.name] = r.CurrentGitInfo()
  return info


# Build rules

def OverrideCMakeCompiler():
  if IsWindows():
    return []
  return ['-DCMAKE_C_COMPILER=' + CC,
          '-DCMAKE_CXX_COMPILER=' + CXX]


def CopyLLVMTools(build_dir, prefix=''):
  # The following isn't useful for now, and takes up space.
  Remove(os.path.join(INSTALL_DIR, prefix, 'bin', 'clang-check'))
  # The following are useful, LLVM_INSTALL_TOOLCHAIN_ONLY did away with them.
  extra_bins = map(Executable,
                   ['FileCheck', 'lli', 'llc', 'llvm-as', 'llvm-dis',
                    'llvm-link', 'llvm-mc', 'llvm-nm', 'llvm-objdump',
                    'llvm-readobj', 'opt'])
  extra_libs = ['libLLVM*.%s' % ext for ext in ['so', 'dylib', 'dll']]
  for p in [glob.glob(os.path.join(build_dir, 'bin', b)) for b in
            extra_bins]:
    for e in p:
      CopyBinaryToArchive(os.path.join(build_dir, 'bin', e), prefix)
  for p in [glob.glob(os.path.join(build_dir, 'lib', l)) for l in
            extra_libs]:
    for e in p:
      CopyLibraryToArchive(os.path.join(build_dir, 'lib', e), prefix)


def BuildEnv(build_dir, use_gnuwin32=False, bin_subdir=False,
             runtime='Release'):
  if not IsWindows():
    return None
  cc_env = host_toolchains.SetUpVSEnv(build_dir)
  if use_gnuwin32:
    cc_env['PATH'] = cc_env['PATH'] + os.pathsep + os.path.join(GNUWIN32_DIR,
                                                                'bin')
  bin_dir = build_dir if not bin_subdir else os.path.join(build_dir, 'bin')
  Mkdir(bin_dir)
  assert runtime in ['Release', 'Debug']
  host_toolchains.CopyDlls(bin_dir, runtime)
  return cc_env


def LLVM():
  buildbot.Step('LLVM')
  Mkdir(LLVM_OUT_DIR)
  cc_env = BuildEnv(LLVM_OUT_DIR, bin_subdir=True)
  build_dylib = 'ON' if not IsWindows() else 'OFF'
  command = [PREBUILT_CMAKE_BIN, '-G', 'Ninja', LLVM_SRC_DIR,
             '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
             '-DLLVM_BUILD_TESTS=ON',
             '-DCMAKE_BUILD_TYPE=Release',
             '-DCMAKE_INSTALL_PREFIX=' + INSTALL_DIR,
             '-DLLVM_INCLUDE_EXAMPLES=OFF',
             '-DCOMPILER_RT_BUILD_XRAY=OFF',
             '-DCOMPILER_RT_INCLUDE_TESTS=OFF',
             '-DCOMPILER_RT_ENABLE_IOS=OFF',
             '-DLLVM_BUILD_LLVM_DYLIB=%s' % build_dylib,
             '-DLLVM_LINK_LLVM_DYLIB=%s' % build_dylib,
             # Our mac bot's toolchain's ld64 is too old for trunk libLTO.
             '-DLLVM_TOOL_LTO_BUILD=OFF',
             '-DLLVM_INSTALL_TOOLCHAIN_ONLY=ON',
             '-DLLVM_ENABLE_ASSERTIONS=ON',
             '-DLLVM_EXPERIMENTAL_TARGETS_TO_BUILD=WebAssembly',
             '-DLLVM_TARGETS_TO_BUILD=X86']

  command.extend(OverrideCMakeCompiler())

  command.extend(host_toolchains.CmakeLauncherFlags())
  jobs = host_toolchains.NinjaJobs()

  proc.check_call(command, cwd=LLVM_OUT_DIR, env=cc_env)
  proc.check_call(['ninja', '-v'] + jobs, cwd=LLVM_OUT_DIR, env=cc_env)
  proc.check_call(['ninja', 'install'] + jobs, cwd=LLVM_OUT_DIR, env=cc_env)
  CopyLLVMTools(LLVM_OUT_DIR)

  if not options.run_tool_tests:
    return

  def RunWithUnixUtils(cmd, **kwargs):
    if IsWindows():
      return proc.check_call(['git', 'bash'] + cmd, **kwargs)
    else:
      return proc.check_call(cmd, **kwargs)

  try:
    buildbot.Step('LLVM regression tests')
    RunWithUnixUtils(['ninja', 'check-all'], cwd=LLVM_OUT_DIR, env=cc_env)
  except proc.CalledProcessError:
    buildbot.FailUnless(lambda: IsWindows())


def V8():
  buildbot.Step('V8')
  proc.check_call([os.path.join(V8_SRC_DIR, 'tools', 'dev', 'v8gen.py'),
                   'x64.release'],
                  cwd=V8_SRC_DIR)
  jobs = host_toolchains.NinjaJobs()
  proc.check_call(['ninja', '-v', '-C', V8_OUT_DIR, 'd8', 'unittests'] + jobs,
                  cwd=V8_SRC_DIR)
  if options.run_tool_tests:
    proc.check_call(['tools/run-tests.py', 'unittests', '--no-presubmit',
                     '--outdir', V8_OUT_DIR],
                    cwd=V8_SRC_DIR)
  # Copy the V8 blobs as well as the ICU data file for timezone data.
  # icudtl.dat is the little-endian version, which goes with x64.
  to_archive = [Executable('d8'), 'natives_blob.bin', 'snapshot_blob.bin',
                'icudtl.dat']
  for a in to_archive:
    CopyBinaryToArchive(os.path.join(V8_OUT_DIR, a))


def Jsc():
  buildbot.Step('JSC')
  Mkdir(JSC_OUT_DIR)

  try:
    command = ['xcrun', PREBUILT_CMAKE_BIN, '-Wno-dev',
               '..', '-G', 'Ninja',
               '-DCMAKE_BUILD_TYPE="Release"',
               '-DPORT=Mac',
               '-DENABLE_WEBASSEMBLY=ON']

    command.extend(OverrideCMakeCompiler())

    jobs = host_toolchains.NinjaJobs()
    command.extend(host_toolchains.CmakeLauncherFlags())

    proc.check_call(command, cwd=JSC_OUT_DIR)
    proc.check_call(['ninja', 'jsc'] + jobs, cwd=JSC_OUT_DIR)
    proc.check_call(['../Tools/Scripts/run-javascriptcore-tests',
                     '--root=bin',
                     '--filter', 'wasm',
                     '--no-build', '--no-testapi', '--no-testmasm',
                     '--no-testb3', '--no-testair', '--fast'],
                    cwd=JSC_OUT_DIR)
    to_archive = [Executable(os.path.join('bin', 'jsc'))]
    for a in to_archive:
      CopyBinaryToArchive(os.path.join(JSC_OUT_DIR, a))

  except proc.CalledProcessError:
    # JSC cmake build is flaky because it is not the official build. For the
    # moment make this not abort the whole process.
    buildbot.Warn()


def Wabt():
  buildbot.Step('WABT')
  Mkdir(WABT_OUT_DIR)
  cc_env = BuildEnv(WABT_OUT_DIR)

  proc.check_call([PREBUILT_CMAKE_BIN, '-G', 'Ninja', WABT_SRC_DIR,
                   '-DCMAKE_BUILD_TYPE=Release',
                   '-DCMAKE_INSTALL_PREFIX=%s' % INSTALL_DIR,
                   '-DBUILD_TESTS=OFF'] + OverrideCMakeCompiler(),
                  cwd=WABT_OUT_DIR, env=cc_env)
  proc.check_call(['ninja'], cwd=WABT_OUT_DIR, env=cc_env)
  # TODO(sbc): git submodules are not yet fetched so we can't yet endable
  # wabt tests.
  # if options.run_tool_tests:
  #   proc.check_call(['ninja', 'run-tests'], cwd=WABT_OUT_DIR, env=cc_env)
  proc.check_call(['ninja', 'install'], cwd=WABT_OUT_DIR, env=cc_env)


def OCaml():
  buildbot.Step('OCaml')
  # Build the ocaml compiler and runtime
  makefile = os.path.join(OCAML_DIR, 'config', 'Makefile')
  if not os.path.isfile(makefile):
    configure = os.path.join(OCAML_DIR, 'configure')
    cc_flag = ['-cc', CC, '-aspp', CC + ' -c']
    if sys.platform == 'darwin':
      cc_flag = []
    proc.check_call(
        [configure, '-prefix', OCAML_OUT_DIR, '--no-ocamldoc'] + cc_flag,
        cwd=OCAML_DIR)
  proc.check_call(['make', 'world.opt', '-j%s' % NPROC], cwd=OCAML_DIR)
  proc.check_call(['make', 'install'], cwd=OCAML_DIR)
  os.environ['PATH'] = OCAML_BIN_DIR + os.pathsep + os.environ['PATH']
  # Build ocamlbuild
  proc.check_call(
      ['make', 'configure', 'OCAMLBUILD_PREFIX=' + OCAML_OUT_DIR],
      cwd=OCAMLBUILD_DIR)
  proc.check_call(['make', '-j%s' % NPROC], cwd=OCAMLBUILD_DIR)
  proc.check_call(['make', 'install', 'CHECK_IF_PREINSTALLED=false'],
                  cwd=OCAMLBUILD_DIR)
  ocamlbuild = os.path.join(OCAML_BIN_DIR, 'ocamlbuild')
  assert os.path.isfile(ocamlbuild), 'Expected installed %s' % ocamlbuild


def Spec():
  buildbot.Step('spec')
  os.environ['PATH'] = OCAML_BIN_DIR + os.pathsep + os.environ['PATH']
  # Spec builds in-tree. Always clobber.
  proc.check_call(['make', 'clean'], cwd=ML_DIR)
  proc.check_call(['make', 'opt'], cwd=ML_DIR)
  if options.run_tool_tests:
    proc.check_call(['make', 'test'], cwd=ML_DIR)
  wasm = os.path.join(ML_DIR, 'wasm')
  CopyBinaryToArchive(wasm)


def Binaryen():
  buildbot.Step('binaryen')
  Mkdir(BINARYEN_OUT_DIR)
  # Currently it's a bad idea to do a non-asserts build of Binaryen
  cc_env = BuildEnv(BINARYEN_OUT_DIR, bin_subdir=True, runtime='Debug')

  proc.check_call(
      [PREBUILT_CMAKE_BIN, '-G', 'Ninja', BINARYEN_SRC_DIR,
       '-DCMAKE_BUILD_TYPE=Release',
       '-DCMAKE_INSTALL_PREFIX=%s' % INSTALL_DIR] + OverrideCMakeCompiler(),
      cwd=BINARYEN_OUT_DIR, env=cc_env)
  proc.check_call(['ninja', '-v'], cwd=BINARYEN_OUT_DIR, env=cc_env)
  proc.check_call(['ninja', 'install'], cwd=BINARYEN_OUT_DIR, env=cc_env)


def Fastcomp():
  buildbot.Step('fastcomp')
  Mkdir(FASTCOMP_OUT_DIR)
  install_dir = os.path.join(INSTALL_DIR, 'fastcomp')
  build_dylib = 'ON' if not IsWindows() else 'OFF'
  cc_env = BuildEnv(FASTCOMP_OUT_DIR, bin_subdir=True)
  command = [PREBUILT_CMAKE_BIN, '-G', 'Ninja', FASTCOMP_SRC_DIR,
             '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
             '-DCMAKE_BUILD_TYPE=Release',
             '-DCMAKE_INSTALL_PREFIX=' + install_dir,
             '-DLLVM_INCLUDE_EXAMPLES=OFF',
             '-DLLVM_BUILD_LLVM_DYLIB=%s' % build_dylib,
             '-DLLVM_LINK_LLVM_DYLIB=%s' % build_dylib,
             '-DLLVM_INSTALL_TOOLCHAIN_ONLY=ON',
             '-DLLVM_TARGETS_TO_BUILD=X86;JSBackend',
             '-DLLVM_ENABLE_ASSERTIONS=ON'] + OverrideCMakeCompiler()

  command.extend(host_toolchains.CmakeLauncherFlags())
  proc.check_call(command, cwd=FASTCOMP_OUT_DIR, env=cc_env)

  jobs = host_toolchains.NinjaJobs()
  proc.check_call(['ninja'] + jobs, cwd=FASTCOMP_OUT_DIR, env=cc_env)
  proc.check_call(['ninja', 'install'], cwd=FASTCOMP_OUT_DIR, env=cc_env)
  # Fastcomp has a different install location than the rest of the tools
  BuildEnv(install_dir, bin_subdir=True)
  CopyLLVMTools(FASTCOMP_OUT_DIR, 'fastcomp')


def Emscripten(use_asm):
  buildbot.Step('emscripten')
  # Remove cached library builds (e.g. libc, libc++) to force them to be
  # rebuilt in the step below.
  Remove(os.path.expanduser(os.path.join('~', '.emscripten_cache')))
  emscripten_dir = os.path.join(INSTALL_DIR, 'emscripten')
  Remove(emscripten_dir)
  print 'Copying directory %s to %s' % (EMSCRIPTEN_SRC_DIR, emscripten_dir)
  shutil.copytree(EMSCRIPTEN_SRC_DIR,
                  emscripten_dir,
                  symlinks=True,
                  # Ignore the big git blob so it doesn't get archived.
                  ignore=shutil.ignore_patterns('.git'))

  def WriteEmscriptenConfig(infile, outfile):
    with open(infile) as config:
      text = config.read().replace('{{WASM_INSTALL}}',
                                   WindowsFSEscape(INSTALL_DIR))
      text = text.replace('{{PREBUILT_NODE}}', WindowsFSEscape(NODE_BIN))
    with open(outfile, 'w') as config:
      config.write(text)

  configs = [('emwasm', EMSCRIPTEN_CONFIG_WASM)]
  if use_asm:
    # build with asm2wasm first to match the ordering of the test steps
    configs.insert(0, ('asm2wasm', EMSCRIPTEN_CONFIG_ASMJS))

  for config_name, config in configs:
    buildbot.Step('emscripten (%s)' % config_name)
    print 'Config file: ', config
    src_config = os.path.join(SCRIPT_DIR, os.path.basename(config))
    WriteEmscriptenConfig(src_config, config)
    try:
      # Use emscripten's embuilder to prebuild the system libraries.
      # This depends on binaryen already being built and installed into the
      # archive/install dir.
      os.environ['EM_CONFIG'] = config
      proc.check_call([
          sys.executable, os.path.join(emscripten_dir, 'embuilder.py'),
          'build', 'SYSTEM'])

    except proc.CalledProcessError:
      # Note the failure but allow the build to continue.
      buildbot.Fail()
    finally:
      del os.environ['EM_CONFIG']

  wrapper = os.path.join(SCRIPT_DIR, 'emcc_wrapper.sh')
  shutil.copy2(wrapper, os.path.join(INSTALL_BIN, 'emcc'))
  shutil.copy2(wrapper, os.path.join(INSTALL_BIN, 'em++'))
  shutil.copy2(wrapper, os.path.join(INSTALL_BIN, 'emconfigure'))
  shutil.copy2(wrapper, os.path.join(INSTALL_BIN, 'emmake'))


def CompilerRT():
  # TODO(sbc): Figure out how to do this step as part of the llvm build.
  # I suspect that this can be done using the llvm/runtimes directory but
  # have yet to make it actually work this way.
  buildbot.Step('compiler-rt')

  # TODO(sbc): Remove this.
  # The compiler-rt doesn't currently rebuild libraries when a new -DCMAKE_AR
  # value is specified.
  if os.path.isdir(COMPILER_RT_OUT_DIR):
    Remove(COMPILER_RT_OUT_DIR)

  Mkdir(COMPILER_RT_OUT_DIR)
  cc_env = BuildEnv(COMPILER_RT_SRC_DIR, bin_subdir=True)
  command = [PREBUILT_CMAKE_BIN, '-G', 'Ninja',
             os.path.join(COMPILER_RT_SRC_DIR, 'lib', 'builtins'),
             '-DCMAKE_TOOLCHAIN_FILE=' +
             os.path.join(INSTALL_DIR, 'wasm_standalone.cmake'),
             # TODO: why doesn't setting CMAKE_AR in the toolchain file work?
             '-DCMAKE_AR=' + os.path.join(INSTALL_BIN, 'llvm-ar'),
             '-DCMAKE_RANLIB=' + os.path.join(INSTALL_BIN, 'llvm-ranlib'),
             '-DCOMPILER_RT_BAREMETAL_BUILD=On',
             '-DCOMPILER_RT_BUILD_XRAY=OFF',
             '-DCOMPILER_RT_INCLUDE_TESTS=OFF',
             '-DCOMPILER_RT_ENABLE_IOS=OFF',
             '-DCOMPILER_RT_DEFAULT_TARGET_ONLY=On',
             '-DLLVM_CONFIG_PATH=' +
             os.path.join(LLVM_OUT_DIR, 'bin', 'llvm-config'),
             '-DCOMPILER_RT_OS_DIR=.',
             '-DCMAKE_INSTALL_PREFIX=' +
             os.path.join(INSTALL_DIR, 'lib', 'clang', '6.0.0')]

  proc.check_call(command, cwd=COMPILER_RT_OUT_DIR, env=cc_env)
  proc.check_call(['ninja', '-v'], cwd=COMPILER_RT_OUT_DIR, env=cc_env)
  proc.check_call(['ninja', 'install'], cwd=COMPILER_RT_OUT_DIR, env=cc_env)


def Musl():
  buildbot.Step('musl')
  Mkdir(MUSL_OUT_DIR)
  path = os.environ['PATH']
  try:
    cc_env = BuildEnv(MUSL_OUT_DIR, use_gnuwin32=True)
    # Build musl directly to wasm object files in an ar library
    proc.check_call([
        os.path.join(MUSL_SRC_DIR, 'libc.py'),
        '--clang_dir', INSTALL_BIN,
        '--binaryen_dir', os.path.join(INSTALL_BIN),
        '--sexpr_wasm', os.path.join(INSTALL_BIN, 'wat2wasm'),
        '--out', os.path.join(MUSL_OUT_DIR, 'libc.a'),
        '--musl', MUSL_SRC_DIR, '--compile-to-wasm'], env=cc_env)
    CopyLibraryToSysroot(os.path.join(MUSL_OUT_DIR, 'libc.a'))
    CopyLibraryToSysroot(os.path.join(MUSL_OUT_DIR, 'crt1.o'))
    CopyLibraryToSysroot(os.path.join(MUSL_SRC_DIR, 'arch', 'wasm32',
                                      'wasm.syms'))

    # Build musl via s2wasm as single wasm file.
    proc.check_call([
        os.path.join(MUSL_SRC_DIR, 'libc.py'),
        '--clang_dir', INSTALL_BIN,
        '--binaryen_dir', os.path.join(INSTALL_BIN),
        '--sexpr_wasm', os.path.join(INSTALL_BIN, 'wat2wasm'),
        '--musl', MUSL_SRC_DIR], cwd=MUSL_OUT_DIR, env=cc_env)
    for f in ['musl.wast', 'musl.wasm']:
      CopyLibraryToArchive(os.path.join(MUSL_OUT_DIR, f))

    wasm_js = os.path.join(MUSL_SRC_DIR, 'arch', 'wasm32', 'wasm.js')
    CopyLibraryToArchive(wasm_js)

    CopyTree(os.path.join(MUSL_SRC_DIR, 'include'),
             os.path.join(INSTALL_SYSROOT, 'include'))
    CopyTree(os.path.join(MUSL_SRC_DIR, 'arch', 'wasm32'),
             os.path.join(INSTALL_SYSROOT, 'include'))
    # Strictly speaking the CMake toolchain file isn't part of musl, but does
    # go along with the headers and libs musl installs
    shutil.copy2(os.path.join(SCRIPT_DIR, 'wasm_standalone.cmake'),
                 INSTALL_DIR)

  except proc.CalledProcessError:
    # Note the failure but allow the build to continue.
    buildbot.Fail()
  finally:
    os.environ['PATH'] = path


def ArchiveBinaries():
  buildbot.Step('Archive binaries')
  # All relevant binaries were copied to the LLVM directory.
  UploadArchive('torture-c', Archive(GCC_TEST_DIR))
  UploadArchive('binaries', Archive(INSTALL_DIR, print_content=True))


def DebianPackage():
  is_linux = sys.platform.startswith('linux')
  if not (is_linux and IsBuildbot()):
    return

  buildbot.Step('Debian package')
  top_dir = os.path.dirname(SCRIPT_DIR)
  try:
    if BUILDBOT_BUILDNUMBER:
      message = ('Automatic build %s produced on http://wasm-stat.us' %
                 BUILDBOT_BUILDNUMBER)
      version = '0.1.' + BUILDBOT_BUILDNUMBER
      proc.check_call(['dch', '-D', 'unstable', '-v', version, message],
                      cwd=top_dir)
    proc.check_call(['debuild', '--no-lintian', '-i', '-us', '-uc', '-b'],
                    cwd=top_dir)
    if BUILDBOT_BUILDNUMBER:
      proc.check_call(['git', 'checkout', 'debian/changelog'], cwd=top_dir)

      debfile = os.path.join(os.path.dirname(top_dir),
                             'wasm-toolchain_%s_amd64.deb' % version)
      UploadFile(debfile, os.path.basename(debfile))
  except proc.CalledProcessError:
    # Note the failure but allow the build to continue.
    buildbot.Fail()
    return


def CompileLLVMTorture(extension, outdir, opt):
  name = 'Compile LLVM Torture (%s, %s)' % (extension, opt)
  buildbot.Step(name)
  c = Executable(os.path.join(INSTALL_BIN, 'clang'))
  cxx = Executable(os.path.join(INSTALL_BIN, 'clang++'))
  Remove(outdir)
  Mkdir(outdir)
  unexpected_result_count = compile_torture_tests.run(
      c=c, cxx=cxx, testsuite=GCC_TEST_DIR,
      sysroot_dir=INSTALL_SYSROOT,
      fails=LLVM_KNOWN_TORTURE_FAILURES,
      out=outdir,
      config='wasm-' + extension,
      opt=opt)
  UploadArchive('torture-%s-%s' % (extension, opt), Archive(outdir))
  if 0 != unexpected_result_count:
    buildbot.Fail()


def CompileLLVMTortureBinaryen(name, em_config, outdir, fails, opt):
  buildbot.Step('Compile LLVM Torture (%s, %s)' % (name, opt))
  os.environ['EM_CONFIG'] = em_config
  c = Executable(os.path.join(INSTALL_DIR, 'emscripten', 'emcc'), '.bat')
  cxx = Executable(os.path.join(INSTALL_DIR, 'emscripten', 'em++'), '.bat')
  Remove(outdir)
  Mkdir(outdir)
  unexpected_result_count = compile_torture_tests.run(
      c=c, cxx=cxx, testsuite=GCC_TEST_DIR,
      sysroot_dir=INSTALL_SYSROOT,
      fails=fails,
      out=outdir,
      config='binaryen-native',
      opt=opt)
  UploadArchive('torture-%s-%s' % (name, opt), Archive(outdir))
  if 0 != unexpected_result_count:
    buildbot.Fail()


def LinkLLVMTorture(name, linker, fails, indir, outdir, extension,
                    opt, args=None):
  buildbot.Step('Link LLVM Torture (%s, %s)' % (name, opt))
  assert os.path.isfile(linker), 'Cannot find linker at %s' % linker
  Remove(outdir)
  Mkdir(outdir)
  input_pattern = os.path.join(indir, '*.' + extension)
  unexpected_result_count = link_assembly_files.run(
      linker=linker, files=input_pattern, fails=fails, attributes=[opt],
      out=outdir, args=args)
  UploadArchive('torture-%s-%s' % (name, opt), Archive(outdir))
  if 0 != unexpected_result_count:
    buildbot.Fail()


def AssembleLLVMTorture(name, assembler, indir, outdir, fails, opt):
  buildbot.Step('Assemble LLVM Torture (%s, %s)' % (name, opt))
  assert os.path.isfile(assembler), 'Cannot find assembler at %s' % assembler
  files = os.path.join(indir, '*.wast')
  Remove(outdir)
  Mkdir(outdir)
  unexpected_result_count = assemble_files.run(
      assembler=assembler,
      files=files,
      fails=fails,
      attributes=[opt],
      out=outdir)
  UploadArchive('torture-%s-%s' % (name, opt), Archive(outdir))
  if 0 != unexpected_result_count:
    buildbot.Fail()


def ExecuteLLVMTorture(name, runner, indir, fails, attributes, extension, opt,
                       outdir='', wasmjs='', extra_files=None,
                       warn_only=False):
  extra_files = [] if extra_files is None else extra_files

  buildbot.Step('Execute LLVM Torture (%s, %s)' % (name, opt))
  if not indir:
    print 'Step skipped: no input'
    buildbot.Warn()
    return None
  assert os.path.isfile(runner), 'Cannot find runner at %s' % runner
  files = os.path.join(indir, '*.%s' % extension)
  unexpected_result_count = execute_files.run(
      runner=runner,
      files=files,
      fails=fails,
      attributes=attributes + [opt],
      out=outdir,
      wasmjs=wasmjs,
      extra_files=extra_files)
  if 0 != unexpected_result_count:
    buildbot.FailUnless(lambda: warn_only)


class Build(object):
  def __init__(self, name_, runnable_,
               no_windows=False, no_linux=False,
               *args, **kwargs):
    self.name = name_
    self.runnable = runnable_
    self.args = args
    self.kwargs = kwargs
    # Almost all of these steps depend directly or indirectly on CMake.
    # Temporarily disable them.
    self.no_windows = no_windows
    self.no_linux = no_linux

  def Run(self):
    if IsWindows() and self.no_windows:
      print "Skipping %s: Doesn't work on windows" % self.runnable.__name__
      return
    if IsLinux() and self.no_linux:
      print "Skipping %s: Doesn't work on Linux" % self.runnable.__name__
      return
    self.runnable(*self.args, **self.kwargs)


def Summary(repos):
  buildbot.Step('Summary')
  info = {'repositories': repos}
  info['build'] = BUILDBOT_BUILDNUMBER
  info['scheduler'] = SCHEDULER
  info_file = os.path.join(INSTALL_DIR, 'buildinfo.json')

  if IsBuildbot():
    info_json = json.dumps(info, indent=2)
    print info_json

    with open(info_file, 'w+') as f:
      f.write(info_json)
      f.write('\n')

  print 'Failed steps: %s.' % buildbot.Failed()
  for step in buildbot.FailedList():
    print '    %s' % step
  print 'Warned steps: %s.' % buildbot.Warned()
  for step in buildbot.WarnedList():
    print '    %s' % step

  if IsBuildbot():
    latest_file = '%s/%s' % (BUILDBOT_BUILDERNAME, 'latest.json')
    buildbot.Link('latest.json', cloud.Upload(info_file, latest_file))

  if buildbot.Failed():
    buildbot.Fail()
  else:
    if IsBuildbot():
      lkgr_file = '%s/%s' % (BUILDBOT_BUILDERNAME, 'lkgr.json')
      buildbot.Link('lkgr.json', cloud.Upload(info_file, lkgr_file))


def AllBuilds(use_asm=False):
  return [
      # Host tools
      Build('llvm', LLVM),
      Build('v8', V8),
      Build('jsc', Jsc, no_windows=True, no_linux=True),
      Build('wabt', Wabt),
      Build('ocaml', OCaml, no_windows=True),
      Build('spec', Spec, no_windows=True),
      Build('binaryen', Binaryen),
      Build('fastcomp', Fastcomp),
      Build('emscripten', Emscripten, use_asm=use_asm),
      # Target libs
      Build('musl', Musl),
      Build('compiler-rt', CompilerRT),
      # Archive
      Build('archive', ArchiveBinaries),
      Build('debian', DebianPackage),
  ]


def BuildRepos(filter, use_asm):
  for rule in filter.Apply(AllBuilds(use_asm)):
    rule.Run()


class Test(object):
  def __init__(self, name_, runnable_, no_windows=False):
    self.name = name_
    self.runnable = runnable_
    self.no_windows = no_windows

  def Test(self):
    if IsWindows() and self.no_windows:
      print "Skipping %s: Doesn't work on windows" % self.runnable.__name__
      return
    self.runnable()


def GetTortureDir(name, opt):
  dirs = {
      's': os.path.join(TORTURE_S_OUT_DIR, opt),
      'o': os.path.join(TORTURE_O_OUT_DIR, opt),
      'asm2wasm': os.path.join(ASM2WASM_TORTURE_OUT_DIR, opt),
      'emwasm': os.path.join(EMSCRIPTENWASM_TORTURE_OUT_DIR, opt)
  }
  if name in dirs:
    return dirs[name]
  return os.path.join(WORK_DIR, 'torture-' + name, opt)


def TestBare():
  # Compile
  for opt in BARE_TEST_OPT_FLAGS:
    CompileLLVMTorture('s', GetTortureDir('s', opt), opt)
  for opt in BARE_TEST_OPT_FLAGS:
    CompileLLVMTorture('o', GetTortureDir('o', opt), opt)

  # Link/Assemble
  for opt in BARE_TEST_OPT_FLAGS:
    LinkLLVMTorture(
        name='lld',
        linker=Executable(os.path.join(INSTALL_BIN, 'clang')),
        fails=LLD_KNOWN_TORTURE_FAILURES,
        indir=GetTortureDir('o', opt),
        outdir=GetTortureDir('lld', opt),
        extension='o',
        opt=opt)
  for opt in BARE_TEST_OPT_FLAGS:
    LinkLLVMTorture(
        name='s2wasm',
        linker=Executable(os.path.join(INSTALL_BIN, 's2wasm')),
        fails=S2WASM_KNOWN_TORTURE_FAILURES,
        indir=GetTortureDir('s', opt),
        outdir=GetTortureDir('s2wasm', opt),
        extension='s',
        opt=opt)
  for opt in BARE_TEST_OPT_FLAGS:
    AssembleLLVMTorture(
        name='wat2wasm',
        assembler=Executable(os.path.join(INSTALL_BIN, 'wat2wasm')),
        indir=GetTortureDir('s2wasm', opt),
        outdir=GetTortureDir('wat2wasm', opt),
        fails=WAT2WASM_KNOWN_TORTURE_FAILURES,
        opt=opt)

  # Execute
  common_attrs = ['bare']

  for opt in BARE_TEST_OPT_FLAGS:
    ExecuteLLVMTorture(
        name='d8-lld',
        runner=Executable(os.path.join(INSTALL_BIN, 'd8')),
        indir=GetTortureDir('lld', opt),
        fails=RUN_KNOWN_TORTURE_FAILURES,
        attributes=common_attrs + ['d8', 'lld'],
        extension='wasm',
        opt=opt,
        wasmjs=os.path.join(INSTALL_LIB, 'wasm.js'))
  for opt in BARE_TEST_OPT_FLAGS:
    ExecuteLLVMTorture(
        name='wasm-shell',
        runner=Executable(os.path.join(INSTALL_BIN, 'wasm-shell')),
        indir=GetTortureDir('s2wasm', opt),
        fails=BINARYEN_SHELL_KNOWN_TORTURE_FAILURES,
        attributes=common_attrs + ['wasm-shell'],
        extension='wast',
        opt=opt,
        warn_only=True)  # TODO wasm-shell is flaky when running tests.

  if not IsWindows():
    for opt in BARE_TEST_OPT_FLAGS:
      ExecuteLLVMTorture(
          name='spec',
          runner=Executable(os.path.join(INSTALL_BIN, 'wasm')),
          indir=GetTortureDir('s2wasm', opt),
          fails=SPEC_KNOWN_TORTURE_FAILURES,
          attributes=common_attrs + ['spec'],
          extension='wast',
          opt=opt)

  for opt in BARE_TEST_OPT_FLAGS:
    ExecuteLLVMTorture(
        name='d8',
        runner=Executable(os.path.join(INSTALL_BIN, 'd8')),
        indir=GetTortureDir('wat2wasm', opt),
        fails=RUN_KNOWN_TORTURE_FAILURES,
        attributes=common_attrs + ['d8'],
        extension='wasm',
        opt=opt,
        wasmjs=os.path.join(INSTALL_LIB, 'wasm.js'))

  if IsMac() and not buildbot.DidStepFailOrWarn('JSC'):
    for opt in BARE_TEST_OPT_FLAGS:
      ExecuteLLVMTorture(
          name='jsc',
          runner=os.path.join(INSTALL_BIN, 'jsc'),
          indir=GetTortureDir('wat2wasm', opt),
          fails=RUN_KNOWN_TORTURE_FAILURES,
          attributes=common_attrs + ['jsc'],
          extension='wasm',
          opt=opt,
          warn_only=True,
          wasmjs=os.path.join(INSTALL_LIB, 'wasm.js'))


def TestAsm():
  for opt in EMSCRIPTEN_TEST_OPT_FLAGS:
    CompileLLVMTortureBinaryen(
        'asm2wasm',
        EMSCRIPTEN_CONFIG_ASMJS,
        GetTortureDir('asm2wasm', opt),
        ASM2WASM_KNOWN_TORTURE_COMPILE_FAILURES,
        opt)
  for opt in EMSCRIPTEN_TEST_OPT_FLAGS:
    ExecuteLLVMTorture(
        name='asm2wasm',
        runner=Executable(os.path.join(INSTALL_BIN, 'd8')),
        indir=GetTortureDir('asm2wasm', opt),
        fails=RUN_KNOWN_TORTURE_FAILURES,
        attributes=['asm2wasm', 'd8'],
        extension='c.js',
        opt=opt,
        # emscripten's wasm.js expects all files in cwd.
        outdir=GetTortureDir('asm2wasm', opt))


def TestEmwasm():
  for opt in EMSCRIPTEN_TEST_OPT_FLAGS:
    CompileLLVMTortureBinaryen(
        'emwasm',
        EMSCRIPTEN_CONFIG_WASM,
        GetTortureDir('emwasm', opt),
        EMSCRIPTENWASM_KNOWN_TORTURE_COMPILE_FAILURES,
        opt)
  for opt in EMSCRIPTEN_TEST_OPT_FLAGS:
    ExecuteLLVMTorture(
        name='emwasm',
        runner=Executable(os.path.join(INSTALL_BIN, 'd8')),
        indir=GetTortureDir('emwasm', opt),
        fails=RUN_KNOWN_TORTURE_FAILURES,
        attributes=['emwasm', 'd8'],
        extension='c.js',
        opt=opt,
        outdir=GetTortureDir('emwasm', opt))


def ExecuteEmscriptenTestSuite(name, config, outdir, warn_only):
  buildbot.Step('Execute emscripten testsuite (%s)' % name)
  Mkdir(outdir)
  try:
    proc.check_call(
        [os.path.join(INSTALL_DIR, 'emscripten', 'tests', 'runner.py'),
         'binaryen2', '--em-config', config],
        cwd=outdir)
  except proc.CalledProcessError:
    buildbot.FailUnless(lambda: warn_only)


def TestEmtest():
  ExecuteEmscriptenTestSuite(
      'emwasm',
      EMSCRIPTEN_CONFIG_WASM,
      EMSCRIPTEN_TEST_OUT_DIR,
      warn_only=False)


def TestEmtestAsm2Wasm():
  ExecuteEmscriptenTestSuite(
      'asm2wasm',
      EMSCRIPTEN_CONFIG_ASMJS,
      EMSCRIPTEN_ASMJS_TEST_OUT_DIR,
      warn_only=False)


def TestWasmSimd():
  script = os.path.join(SCRIPT_DIR, 'test_wasm_simd.py')
  clang = Executable(os.path.join(INSTALL_BIN, 'clang'))
  include = os.path.join(EMSCRIPTEN_SRC_DIR, 'system', 'include')
  try:
    proc.check_call([script, clang, include])
  except proc.CalledProcessError:
    buildbot.Fail()


ALL_TESTS = [
    Test('bare', TestBare),
    Test('asm', TestAsm),
    Test('emwasm', TestEmwasm),
    Test('emtest', TestEmtest, no_windows=True),
    Test('emtest-asm', TestEmtestAsm2Wasm, no_windows=True),
    Test('wasm-simd', TestWasmSimd),
]


def TextWrapNameList(prefix, items):
  width = 80  # TODO(binji): better guess?
  names = sorted(item.name for item in items)
  return '%s%s' % (prefix, textwrap.fill(' '.join(names), width,
                                         initial_indent='  ',
                                         subsequent_indent='  '))


def ParseArgs():
  def SplitComma(arg):
    if not arg:
      return None
    return arg.split(',')

  epilog = '\n\n'.join([
      TextWrapNameList('sync targets:\n', ALL_SOURCES),
      TextWrapNameList('build targets:\n', AllBuilds()),
      TextWrapNameList('test targets:\n', ALL_TESTS),
  ])

  parser = argparse.ArgumentParser(
      description='Wasm waterfall top-level CI script',
      formatter_class=argparse.RawDescriptionHelpFormatter,
      epilog=epilog)
  sync_grp = parser.add_mutually_exclusive_group()
  sync_grp.add_argument(
      '--no-sync', dest='sync', default=True, action='store_false',
      help='Skip fetching and checking out source repos')
  sync_grp.add_argument(
      '--sync-include', dest='sync_include', default='', type=SplitComma,
      help='Include only the comma-separated list of sync targets')
  sync_grp.add_argument(
      '--sync-exclude', dest='sync_exclude', default='', type=SplitComma,
      help='Include only the comma-separated list of sync targets')

  parser.add_argument(
      '--sync-lkgr', dest='sync_lkgr', default=False, action='store_true',
      help='When syncing, only sync up to the Last Known Good Revision '
           'for each sync target')

  build_grp = parser.add_mutually_exclusive_group()
  build_grp.add_argument(
      '--no-build', dest='build', default=True, action='store_false',
      help='Skip building source repos (also skips V8 and LLVM unit tests)')
  build_grp.add_argument(
      '--build-include', dest='build_include', default='', type=SplitComma,
      help='Include only the comma-separated list of build targets')
  build_grp.add_argument(
      '--build-exclude', dest='build_exclude', default='', type=SplitComma,
      help='Include only the comma-separated list of build targets')

  test_grp = parser.add_mutually_exclusive_group()
  test_grp.add_argument(
      '--no-test', dest='test', default=True, action='store_false',
      help='Skip running tests')
  test_grp.add_argument(
      '--test-include', dest='test_include', default='', type=SplitComma,
      help='Include only the comma-separated list of test targets')
  test_grp.add_argument(
      '--test-exclude', dest='test_exclude', default='', type=SplitComma,
      help='Include only the comma-separated list of test targets')

  parser.add_argument(
      '--no-tool-tests', dest='run_tool_tests', action='store_false',
      help='Skip the testing of tools (such tools llvm, wabt, v8, spec)')
  parser.add_argument(
      '--git-status', dest='git_status', default=False, action='store_true',
      help='Show git status for each sync target. '
           "Doesn't sync, build, or test")

  return parser.parse_args()


def run(sync_filter, build_filter, test_filter):
  if options.git_status:
    for s in ALL_SOURCES:
      s.PrintGitStatus()
    return 0

  Clobber()
  Chdir(SCRIPT_DIR)
  Mkdir(WORK_DIR)
  SyncRepos(sync_filter, options.sync_lkgr)
  repos = GetRepoInfo() if IsBuildbot() else {}
  if build_filter.All():
    Remove(INSTALL_DIR)
    Mkdir(INSTALL_DIR)
    Mkdir(INSTALL_BIN)
    Mkdir(INSTALL_LIB)

  # Add prebuilt cmake to PATH so any subprocesses use a consistent cmake.
  os.environ['PATH'] = (os.path.join(PREBUILT_CMAKE_DIR, 'bin') +
                        os.pathsep + os.environ['PATH'])

  # TODO(dschuff): Figure out how to make these statically linked?
  if IsWindows():
    host_toolchains.CopyDlls(INSTALL_BIN, 'Debug')

  try:
    BuildRepos(build_filter,
               test_filter.Check('asm') or test_filter.Check('emtest-asm'))
  except Exception:
    # If any exception reaches here, do not attempt to run the tests; just
    # log the error for buildbot and exit
    print "Exception thrown in build step."
    traceback.print_exc()
    buildbot.Fail()
    Summary(repos)
    return 1

  for t in test_filter.Apply(ALL_TESTS):
    t.Test()

  # Keep the summary step last: it'll be marked as red if the return code is
  # non-zero. Individual steps are marked as red with buildbot.Fail().
  Summary(repos)
  return buildbot.Failed()


def main():
  global options
  start = time.time()
  options = ParseArgs()

  sync_include = options.sync_include if options.sync else []
  sync_filter = Filter('sync', sync_include, options.sync_exclude)
  build_include = options.build_include if options.build else []
  build_filter = Filter('build', build_include, options.build_exclude)
  test_include = options.test_include if options.test else []
  test_filter = Filter('test', test_include, options.test_exclude)

  if IsBuildbot():
    # Chrome's buildbot infra includes in its paths a module called 'tools'
    # which conflicts with emscripten's own 'tools' module and overrides the
    # emscripten test runner's import. We don't need that infra in this script,
    # so we just scrub it from the environment.
    del os.environ['PYTHONPATH']

  try:
    ret = run(sync_filter, build_filter, test_filter)
    print 'Completed in {}s'.format(time.time() - start)
    return ret
  except:
    traceback.print_exc()
    # If an except is raised during one of the steps we still need to
    # print the @@@STEP_FAILURE@@@ annotation otherwise the annotator
    # makes the failed stap as green:
    # TODO(sbc): Remove this if the annotator is fixed: http://crbug.com/647357
    if buildbot.current_step:
      buildbot.Fail()
    return 1


if __name__ == '__main__':
  sys.exit(main())
