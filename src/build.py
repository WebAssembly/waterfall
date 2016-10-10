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

import errno
import glob
import json
import multiprocessing
import os
import shutil
import sys
import tarfile
import tempfile
import traceback
import urllib2

import assemble_files
import buildbot
import cloud
import compile_torture_tests
import execute_files
import link_assembly_files
import proc


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.path.join(SCRIPT_DIR, 'work')

LLVM_SRC_DIR = os.path.join(WORK_DIR, 'llvm')
CLANG_SRC_DIR = os.path.join(LLVM_SRC_DIR, 'tools', 'clang')
COMPILER_RT_SRC_DIR = os.path.join(LLVM_SRC_DIR, 'projects', 'compiler-rt')
LLVM_TEST_SUITE_SRC_DIR = os.path.join(WORK_DIR, 'llvm-test-suite')

EMSCRIPTEN_SRC_DIR = os.path.join(WORK_DIR, 'emscripten')
FASTCOMP_SRC_DIR = os.path.join(WORK_DIR, 'emscripten-fastcomp')

GCC_SRC_DIR = os.path.join(WORK_DIR, 'gcc')
GCC_TEST_DIR = os.path.join(GCC_SRC_DIR, 'gcc', 'testsuite')

V8_SRC_DIR = os.path.join(WORK_DIR, 'v8', 'v8')

WABT_SRC_DIR = os.path.join(WORK_DIR, 'wabt')

SPEC_SRC_DIR = os.path.join(WORK_DIR, 'spec')
ML_DIR = os.path.join(SPEC_SRC_DIR, 'ml-proto')
BINARYEN_SRC_DIR = os.path.join(WORK_DIR, 'binaryen')
MUSL_SRC_DIR = os.path.join(WORK_DIR, 'musl')

FIND_SVN_REV = os.path.join(SCRIPT_DIR, 'find_svn_rev.py')

PREBUILT_CLANG = os.path.join(WORK_DIR, 'chromium-clang')
PREBUILT_CLANG_TOOLS_CLANG = os.path.join(PREBUILT_CLANG, 'tools', 'clang')
PREBUILT_CLANG_BIN = os.path.join(
    PREBUILT_CLANG, 'third_party', 'llvm-build', 'Release+Asserts', 'bin')
CC = os.path.join(PREBUILT_CLANG_BIN, 'clang')
CXX = os.path.join(PREBUILT_CLANG_BIN, 'clang++')

# The archive itself contains the 'cmake343' directory.
PREBUILT_CMAKE_DIR = os.path.join(WORK_DIR, 'cmake343')
PREBUILT_CMAKE_ARCHIVE = 'cmake343_%s.tgz'
PREBUILT_CMAKE_URL = ('https://commondatastorage.googleapis.com/' +
                      'chromium-browser-clang/tools/')
PREBUILT_CMAKE_BIN = os.path.join(PREBUILT_CMAKE_DIR, 'bin', 'cmake')

LLVM_OUT_DIR = os.path.join(WORK_DIR, 'llvm-out')
V8_OUT_DIR = os.path.join(V8_SRC_DIR, 'out.gn', 'x64.release')
WABT_OUT_DIR = os.path.join(WORK_DIR, 'wabt-out')
BINARYEN_OUT_DIR = os.path.join(WORK_DIR, 'binaryen-out')
FASTCOMP_OUT_DIR = os.path.join(WORK_DIR, 'fastcomp-out')
MUSL_OUT_DIR = os.path.join(WORK_DIR, 'musl-out')
TORTURE_S_OUT_DIR = os.path.join(WORK_DIR, 'torture-s')
ASM2WASM_TORTURE_OUT_DIR = os.path.join(WORK_DIR, 'asm2wasm-torture-out')
EMSCRIPTENWASM_TORTURE_OUT_DIR = os.path.join(WORK_DIR, 'emwasm-torture-out')
EMSCRIPTEN_TEST_OUT_DIR = os.path.join(WORK_DIR, 'emtest-out')

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
LLVM_OFFICIAL_MIRROR_BASE = GIT_MIRROR_BASE + 'external/llvm.org/'
GITHUB_MIRROR_BASE = GIT_MIRROR_BASE + 'external/github.com/'
LLVM_GITHUB_MIRROR_BASE = GITHUB_MIRROR_BASE + 'llvm-mirror/'
WASM_GIT_BASE = GITHUB_MIRROR_BASE + 'WebAssembly/'
EMSCRIPTEN_GIT_BASE = GITHUB_MIRROR_BASE + 'kripken/'

# Name of remote for build script to use. Don't touch origin to avoid
# clobbering any local development.
WATERFALL_REMOTE = '_waterfall'

# Sync OCaml from a cached tar file because the upstream repository is only
# http. The file untars into a directory of the same name as the tar file.
OCAML_STORAGE_BASE = 'https://wasm.storage.googleapis.com/'
OCAML_VERSION = 'ocaml-4.02.2'
OCAML_TAR_NAME = OCAML_VERSION + '.tar.gz'
OCAML_TAR = os.path.join(WORK_DIR, OCAML_TAR_NAME)
OCAML_URL = OCAML_STORAGE_BASE + OCAML_TAR_NAME
OCAML_DIR = os.path.join(WORK_DIR, OCAML_VERSION)
OCAML_OUT_DIR = os.path.join(WORK_DIR, 'ocaml-out')
OCAML_BIN_DIR = os.path.join(OCAML_OUT_DIR, 'bin')

# Known failures.
IT_IS_KNOWN = 'known_gcc_test_failures.txt'
LLVM_KNOWN_TORTURE_FAILURES = os.path.join(LLVM_SRC_DIR, 'lib', 'Target',
                                           'WebAssembly', IT_IS_KNOWN)
ASM2WASM_KNOWN_TORTURE_COMPILE_FAILURES = os.path.join(
    SCRIPT_DIR, 'test', 'asm2wasm_compile_' + IT_IS_KNOWN)
EMSCRIPTENWASM_KNOWN_TORTURE_COMPILE_FAILURES = os.path.join(
    SCRIPT_DIR, 'test', 'emwasm_compile_' + IT_IS_KNOWN)

V8_KNOWN_TORTURE_FAILURES = os.path.join(SCRIPT_DIR, 'test',
                                         'd8_' + IT_IS_KNOWN)
V8_MUSL_KNOWN_TORTURE_FAILURES = os.path.join(SCRIPT_DIR, 'test',
                                              'd8_musl_' + IT_IS_KNOWN)
WAST2WASM_KNOWN_TORTURE_FAILURES = os.path.join(WABT_SRC_DIR, 's2wasm_' +
                                                IT_IS_KNOWN)
SPEC_KNOWN_TORTURE_FAILURES = os.path.join(SCRIPT_DIR, 'test',
                                           'spec_' + IT_IS_KNOWN)
S2WASM_KNOWN_TORTURE_FAILURES = os.path.join(BINARYEN_SRC_DIR, 'test',
                                             's2wasm_' + IT_IS_KNOWN)
BINARYEN_SHELL_KNOWN_TORTURE_FAILURES = (
    os.path.join(BINARYEN_SRC_DIR, 'test',
                 's2wasm_known_binaryen_shell_test_failures.txt'))

ASM2WASM_KNOWN_TORTURE_FAILURES = os.path.join(
    SCRIPT_DIR, 'test', 'asm2wasm_run_' + IT_IS_KNOWN)
EMSCRIPTENWASM_KNOWN_TORTURE_FAILURES = os.path.join(
    SCRIPT_DIR, 'test', 'emwasm_run_' + IT_IS_KNOWN)


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


# Shell utilities

def Chdir(path):
  print 'Change directory to: %s' % path
  os.chdir(path)


def Mkdir(path):
  """Create a directory at a specified path.

  Creates all intermediate directories along the way.
  e.g.: Mkdir('a/b/c') when 'a/' is an empty directory will
        cause the creation of directories 'a/b/' and 'a/b/c/'.

  If the path already exists (and is already a directory), this does nothing.
  """
  try:
    os.makedirs(path)
  except OSError as e:
    if not os.path.isdir(path):
      raise Exception('Path %s is not a directory!' % path)
    if not e.errno == errno.EEXIST:
      raise e


def Remove(path):
  """Remove file or directory if it exists, do nothing otherwise."""
  if os.path.exists(path):
    print 'Removing %s' % path
    if os.path.isdir(path):
      shutil.rmtree(path)
    else:
      os.remove(path)


def CopyTree(src, dst):
  """Recursively copy the items in the src directory to the dst directory.

  Unlike shutil.copytree, the destination directory and any subdirectories and
  files may exist. Existing directories are left untouched, and existing files
  are removed and copied from the source using shutil.copy2. It is also not
  symlink-aware.

  Args:
    src: Source. Must be an existing directory.
    dst: Destination directory. If it exists, must be a directory. Otherwise it
         will be created, along with parent directories.
  """
  print 'Copying directory %s to %s' % (src, dst)
  if not os.path.isdir(dst):
    os.makedirs(dst)
  for root, dirs, files in os.walk(src):
    relroot = os.path.relpath(root, src)
    dstroot = os.path.join(dst, relroot)
    for d in dirs:
      dstdir = os.path.join(dstroot, d)
      if not os.path.isdir(dstdir):
        os.mkdir(dstdir)
    for f in files:
      dstfile = os.path.join(dstroot, f)
      if os.path.isfile(dstfile):
        os.remove(dstfile)
      shutil.copy2(os.path.join(root, f), dstfile)


def CopyBinaryToArchive(binary, install_subdir=''):
  """All binaries are archived in the same tar file."""
  install_bin = os.path.join(INSTALL_DIR, install_subdir, 'bin')
  print 'Copying binary %s to archive %s' % (binary, install_bin)
  Mkdir(install_bin)
  shutil.copy2(binary, install_bin)


def CopyLibraryToArchive(library, install_subdir=''):
  """All libraries are archived in the same tar file."""
  install_lib = os.path.join(INSTALL_DIR, install_subdir, 'lib')
  print 'Copying library %s to archive %s' % (library, install_lib)
  Mkdir(install_lib)
  shutil.copy2(library, install_lib)


def Git(cmd, **kwargs):
  """Invoke git."""
  return proc.check_output(
      ['git'] + cmd, shell=sys.platform == 'win32', **kwargs)


def Gclient(cmd, **kwargs):
  """Invoke gclient."""
  return proc.check_output(
      ['gclient'] + cmd, shell=sys.platform == 'win32', **kwargs)


def Tar(directory, print_content=False):
  """Create a tar file from directory."""
  if not IsBuildbot():
    return
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


def UploadFile(local_name, remote_name):
  """Archive the file with the given name, and with the LLVM git hash."""
  if not IsBuildbot():
    return
  buildbot.Link('download', cloud.Upload(local_name, '%s/%s/%s' % (
      BUILDBOT_BUILDERNAME, BUILDBOT_BUILDNUMBER, remote_name)))


def Archive(name, tar):
  """Archive the tar file with the given name, and with the LLVM git hash."""
  if not IsBuildbot():
    return
  UploadFile(tar, 'wasm-%s-%s.tbz2' % (name, BUILDBOT_BUILDNUMBER))


# Repo and subproject utilities

def GitRemoteUrl(cwd, remote):
  """Get the URL of a remote."""
  return Git(['config', '--get', 'remote.%s.url' % remote], cwd=cwd).strip()


def HasRemote(cwd, remote):
  """"Checked whether the named remote exists."""
  remotes = Git(['remote'], cwd=cwd).strip().splitlines()
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
  Git(['remote', 'add', GITHUB_REMOTE, remote], cwd=cwd)


def GitConfigRebaseMaster(cwd):
  """Avoid generating a non-linear history in the clone

  The upstream repository is in Subversion. Use `git pull --rebase` instead of
  git pull: llvm.org/docs/GettingStarted.html#git-mirror
  """
  Git(['config', 'branch.master.rebase', 'true'], cwd=cwd)


def RemoteBranch(branch):
  """Get the remote-qualified branch name to use for waterfall"""
  return WATERFALL_REMOTE + '/' + branch


def IsBuildbot():
  """Return True if we are running on bot, False otherwise."""
  return BUILDBOT_BUILDNUMBER is not None


def GitUpdateRemote(src_dir, git_repo, remote_name):
  try:
    Git(['remote', 'set-url', remote_name, git_repo], cwd=src_dir)
  except proc.CalledProcessError:
    # If proc.check_call fails it throws an exception. 'git remote set-url'
    # fails when the remote doesn't exist, so we should try to add it.
    Git(['remote', 'add', remote_name, git_repo], cwd=src_dir)


class Source(object):
  """Metadata about a sync-able source repo on the waterfall"""
  def __init__(self, name, src_dir, git_repo,
               checkout=RemoteBranch('master'), depth=None,
               custom_sync=None):
    self.name = name
    self.src_dir = src_dir
    self.git_repo = git_repo
    self.checkout = checkout
    self.depth = depth
    self.custom_sync = custom_sync

  def Sync(self, good_hashes=None):
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
      Git(clone)

    GitUpdateRemote(self.src_dir, self.git_repo, WATERFALL_REMOTE)
    Git(['fetch', WATERFALL_REMOTE], cwd=self.src_dir)
    if not self.checkout.startswith(WATERFALL_REMOTE + '/'):
      sys.stderr.write(('WARNING: `git checkout %s` not based on waterfall '
                        'remote (%s), checking out local branch'
                        % (self.checkout, WATERFALL_REMOTE)))
    Git(['checkout', self.checkout], cwd=self.src_dir)
    AddGithubRemote(self.src_dir)

  def CurrentGitInfo(self):
    if not os.path.exists(self.src_dir):
      return None

    def pretty(fmt):
      return Git(
          ['log', '-n1', '--pretty=format:%s' % fmt],
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
      Git(['status'], cwd=self.src_dir)
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
    Gclient(['config', git_repo], cwd=parent)
    Git(['clone', git_repo], cwd=parent)

  GitUpdateRemote(work_dir, git_repo, WATERFALL_REMOTE)
  Git(['fetch', WATERFALL_REMOTE], cwd=work_dir)
  Git(['checkout', checkout], cwd=work_dir)
  Gclient(['sync'], cwd=work_dir)
  return (name, work_dir)


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


def SyncPrebuiltCMake(name, src_dir, git_repo):
  if os.path.isdir(PREBUILT_CMAKE_DIR):
    print 'Prebuilt CMake directory already exists'
  else:
    platform = 'Darwin' if sys.platform == 'darwin' else 'Linux'
    filename = PREBUILT_CMAKE_ARCHIVE % platform
    url = PREBUILT_CMAKE_URL + filename
    Mkdir(PREBUILT_CMAKE_DIR)
    try:
      response = urllib2.urlopen(url)
      data = response.read()
      print 'Downloaded %s' % url
      with tempfile.TemporaryFile() as f:
        f.write(data)
        f.seek(0)
        # The tar file itself includes the 'cmake343' directory, so set the
        # extract path to WORK_DIR to get the right path
        tarfile.open(mode='r:gz', fileobj=f).extractall(path=WORK_DIR)
        assert os.path.isfile(PREBUILT_CMAKE_BIN)
      print 'Extracted CMake to %s' % PREBUILT_CMAKE_DIR
    except urllib2.URLError as e:
      print 'Error downloading %s: %s' % (url, e)
      raise


def NoSync(*args):
  pass

ALL_SOURCES = [
    Source('waterfall', SCRIPT_DIR, None, custom_sync=NoSync),
    Source('llvm', LLVM_SRC_DIR,
           LLVM_GITHUB_MIRROR_BASE + 'llvm'),
    Source('clang', CLANG_SRC_DIR,
           LLVM_GITHUB_MIRROR_BASE + 'clang'),
    Source('compiler-rt', COMPILER_RT_SRC_DIR,
           LLVM_OFFICIAL_MIRROR_BASE + 'compiler-rt'),
    # TODO(dschuff): re-enable this when we switch back to external/llvm.org
    # as the git mirror base, or when we actually begin to use it.
    # Source('llvm-test-suite', LLVM_TEST_SUITE_SRC_DIR,
    #        LLVM_MIRROR_BASE + 'test-suite'),
    Source('emscripten', EMSCRIPTEN_SRC_DIR,
           EMSCRIPTEN_GIT_BASE + 'emscripten',
           checkout=RemoteBranch('incoming')),
    Source('fastcomp', FASTCOMP_SRC_DIR,
           EMSCRIPTEN_GIT_BASE + 'emscripten-fastcomp',
           checkout=RemoteBranch('incoming')),
    Source('fastcomp-clang',
           os.path.join(FASTCOMP_SRC_DIR, 'tools', 'clang'),
           EMSCRIPTEN_GIT_BASE + 'emscripten-fastcomp-clang',
           checkout=RemoteBranch('incoming')),
    Source('gcc', GCC_SRC_DIR,
           GIT_MIRROR_BASE + 'chromiumos/third_party/gcc',
           checkout=GCC_REVISION, depth=GCC_CLONE_DEPTH),
    Source('v8', V8_SRC_DIR,
           GIT_MIRROR_BASE + 'v8/v8',
           custom_sync=ChromiumFetchSync),
    Source('chromium-clang', PREBUILT_CLANG,
           GIT_MIRROR_BASE + 'chromium/src/tools/clang',
           custom_sync=SyncPrebuiltClang),
    Source('cmake', '', '',  # The source and git args are ignored.
           custom_sync=SyncPrebuiltCMake),
    Source('wabt', WABT_SRC_DIR,
           WASM_GIT_BASE + 'wabt.git'),
    Source('spec', SPEC_SRC_DIR,
           WASM_GIT_BASE + 'spec.git',
           checkout=RemoteBranch('binary-0xc')),
    Source('binaryen', BINARYEN_SRC_DIR,
           WASM_GIT_BASE + 'binaryen.git'),
    Source('musl', MUSL_SRC_DIR,
           WASM_GIT_BASE + 'musl.git',
           checkout=RemoteBranch('wasm-prototype-1'))
]


def CurrentSvnRev(path):
  return int(proc.check_output([FIND_SVN_REV, 'HEAD'], cwd=path).strip())


def FindPriorSvnRev(path, goal):
  revs = Git(
      ['rev-list', RemoteBranch('master')], cwd=path).splitlines()
  for rev in revs:
    num = proc.check_output([FIND_SVN_REV, rev], cwd=path).strip()
    if int(num) <= goal:
      return rev
  raise Exception('Cannot find svn rev at or before %d' % goal)


def SyncToSameSvnRev(primary, secondary):
    """Use primary's SVN rev to figure out which rev secondary goes to."""
    primary_svn_rev = CurrentSvnRev(primary)
    print 'SVN REV for %s: %d' % (primary, primary_svn_rev)
    print 'Finding prior %s rev' % secondary
    prior_rev = FindPriorSvnRev(secondary, primary_svn_rev)
    print 'Checking out %s rev: %s' % (secondary, prior_rev)
    Git(['checkout', prior_rev], cwd=secondary)


def SyncLLVMClang(good_hashes=None):
  def get_rev(rev_name):
    if good_hashes and good_hashes.get(rev_name):
      return good_hashes[rev_name]
    elif SCHEDULER == rev_name:
      return BUILDBOT_REVISION
    else:
      return RemoteBranch('master')

  Git(['checkout', get_rev('llvm')], cwd=LLVM_SRC_DIR)
  Git(['checkout', get_rev('clang')], cwd=CLANG_SRC_DIR)
  # If LLVM didn't trigger the new build then sync LLVM to the corresponding
  # clang revision, even if clang may not have triggered the build: usually
  # LLVM provides APIs which clang uses, which means that most synchronized
  # commits touch LLVM before clang. This should reduce the chance of breakage.
  primary = LLVM_SRC_DIR if SCHEDULER == 'llvm' else CLANG_SRC_DIR
  secondary = LLVM_SRC_DIR if primary == CLANG_SRC_DIR else CLANG_SRC_DIR
  SyncToSameSvnRev(primary, secondary)


def SyncOCaml():
  if os.path.isdir(OCAML_DIR):
    print 'OCaml directory already exists'
  else:
    print 'Downloading OCaml %s from %s' % (OCAML_VERSION, OCAML_URL)
    f = urllib2.urlopen(OCAML_URL)
    print 'URL: %s' % f.geturl()
    print 'Info: %s' % f.info()
    with open(OCAML_TAR, 'wb') as out:
      out.write(f.read())
    proc.check_call(['tar', '-xvf', OCAML_TAR], cwd=WORK_DIR)
    assert os.path.isdir(OCAML_DIR), 'Untar should produce %s' % OCAML_DIR


def Clobber():
  if os.environ.get('BUILDBOT_CLOBBER'):
    buildbot.Step('Clobbering work dir')
    if os.path.isdir(WORK_DIR):
      shutil.rmtree(WORK_DIR)


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


def SyncRepos(filter, sync_lkgr=False):
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
  if filter.Check('clang'):
    SyncLLVMClang(good_hashes)
  if filter.Check('ocaml'):
    SyncOCaml()


def GetRepoInfo():
  """Collect a readable form of all repo information here, preventing the
  summary from getting out of sync with the actual list of repos."""
  info = {}
  for r in ALL_SOURCES:
    info[r.name] = r.CurrentGitInfo()
  return info


def Which(name):
  """Find an executable on the system by name. If not found return ''."""
  # If we want to run this on Windows, we'll have to be smarter.
  try:
    o = proc.check_output(['which', name])
    return o.strip()
  except proc.CalledProcessError:
    return ''


def CopyLLVMTools(build_dir, install_subdir=''):
  # The following isn't useful for now, and takes up space.
  Remove(os.path.join(INSTALL_DIR, install_subdir, 'bin', 'clang-check'))
  # The following are useful, LLVM_INSTALL_TOOLCHAIN_ONLY did away with them.
  extra_bins = ['FileCheck', 'lli', 'llc', 'llvm-as', 'llvm-dis', 'llvm-link',
                'llvm-nm', 'opt']
  extra_libs = ['libLLVM*.so']
  for p in [glob.glob(os.path.join(build_dir, 'bin', b)) for b in
            extra_bins]:
    for e in p:
      CopyBinaryToArchive(os.path.join(build_dir, 'bin', e), install_subdir)
  for p in [glob.glob(os.path.join(build_dir, 'lib', l)) for l in
            extra_libs]:
    for e in p:
      CopyLibraryToArchive(os.path.join(build_dir, 'lib', e), install_subdir)


def LLVM():
  buildbot.Step('LLVM')
  Mkdir(LLVM_OUT_DIR)
  command = [PREBUILT_CMAKE_BIN, '-G', 'Ninja', LLVM_SRC_DIR,
             '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
             '-DLLVM_BUILD_TESTS=ON',
             '-DCMAKE_C_COMPILER=' + CC,
             '-DCMAKE_CXX_COMPILER=' + CXX,
             '-DCMAKE_BUILD_TYPE=Release',
             '-DCMAKE_INSTALL_PREFIX=' + INSTALL_DIR,
             '-DLLVM_INCLUDE_EXAMPLES=OFF',
             '-DCOMPILER_RT_BUILD_XRAY=OFF',
             '-DCOMPILER_RT_INCLUDE_TESTS=OFF',
             '-DLLVM_BUILD_LLVM_DYLIB=ON',
             '-DLLVM_LINK_LLVM_DYLIB=ON',
             '-DLLVM_INSTALL_TOOLCHAIN_ONLY=ON',
             '-DLLVM_ENABLE_ASSERTIONS=ON',
             '-DLLVM_EXPERIMENTAL_TARGETS_TO_BUILD=WebAssembly',
             '-DLLVM_TARGETS_TO_BUILD=X86']

  compiler_launcher = None
  jobs = []
  if 'GOMA_DIR' in os.environ:
    compiler_launcher = os.path.join(os.environ['GOMA_DIR'], 'gomacc')
    jobs = ['-j', '50']
  else:
    ccache = Which('ccache')
    if ccache:
      compiler_launcher = ccache
      command.extend(['-DCMAKE_%s_FLAGS=-Qunused-arguments' %
                      c for c in ['C', 'CXX']])

  if compiler_launcher:
    command.extend(['-DCMAKE_%s_COMPILER_LAUNCHER=%s' %
                    (c, compiler_launcher) for c in ['C', 'CXX']])

  proc.check_call(command, cwd=LLVM_OUT_DIR)
  proc.check_call(['ninja', '-v'] + jobs, cwd=LLVM_OUT_DIR)
  proc.check_call(['ninja', 'check-all'], cwd=LLVM_OUT_DIR)
  proc.check_call(['ninja', 'install'] + jobs, cwd=LLVM_OUT_DIR)
  CopyLLVMTools(LLVM_OUT_DIR)


def V8():
  buildbot.Step('V8')
  proc.check_call([sys.executable,
                   os.path.join(V8_SRC_DIR, 'tools', 'dev', 'v8gen.py'),
                   'x64.release'],
                  cwd=V8_SRC_DIR)
  jobs = []
  if 'GOMA_DIR' in os.environ:
    jobs = ['-j', '50']
  proc.check_call(['ninja', '-v', '-C', V8_OUT_DIR, 'd8', 'unittests'] + jobs,
                  cwd=V8_SRC_DIR)
  proc.check_call(['tools/run-tests.py', 'unittests', '--no-presubmit',
                   '--shell-dir', V8_OUT_DIR],
                  cwd=V8_SRC_DIR)
  to_archive = ['d8', 'natives_blob.bin', 'snapshot_blob.bin']
  for a in to_archive:
    CopyBinaryToArchive(os.path.join(V8_OUT_DIR, a))


def Wabt():
  buildbot.Step('WABT')
  Mkdir(WABT_OUT_DIR)
  proc.check_call([PREBUILT_CMAKE_BIN, '-G', 'Ninja', WABT_SRC_DIR,
                   '-DCMAKE_C_COMPILER=%s' % CC,
                   '-DCMAKE_CXX_COMPILER=%s' % CXX,
                   '-DCMAKE_INSTALL_PREFIX=%s' % INSTALL_DIR,
                   '-DBUILD_TESTS=OFF'],
                  cwd=WABT_OUT_DIR)
  proc.check_call(['ninja'], cwd=WABT_OUT_DIR)
  proc.check_call(['ninja', 'install'], cwd=WABT_OUT_DIR)


def OCaml():
  buildbot.Step('OCaml')
  makefile = os.path.join(OCAML_DIR, 'config', 'Makefile')
  if not os.path.isfile(makefile):
    configure = os.path.join(OCAML_DIR, 'configure')
    proc.check_call(
        [configure, '-prefix', OCAML_OUT_DIR, '-cc', CC], cwd=OCAML_DIR)
  proc.check_call(['make', 'world.opt', '-j%s' % NPROC], cwd=OCAML_DIR)
  proc.check_call(['make', 'install'], cwd=OCAML_DIR)
  ocamlbuild = os.path.join(OCAML_BIN_DIR, 'ocamlbuild')
  assert os.path.isfile(ocamlbuild), 'Expected installed %s' % ocamlbuild
  os.environ['PATH'] = OCAML_BIN_DIR + os.pathsep + os.environ['PATH']


def Spec():
  buildbot.Step('spec')
  # Spec builds in-tree. Always clobber and run the tests.
  proc.check_call(['make', 'clean'], cwd=ML_DIR)
  proc.check_call(['make', 'all'], cwd=ML_DIR)
  wasm = os.path.join(ML_DIR, 'wasm.opt')
  CopyBinaryToArchive(wasm)


def Binaryen():
  buildbot.Step('binaryen')
  Mkdir(BINARYEN_OUT_DIR)
  proc.check_call(
      [PREBUILT_CMAKE_BIN, '-G', 'Ninja', BINARYEN_SRC_DIR,
       '-DCMAKE_C_COMPILER=' + CC,
       '-DCMAKE_CXX_COMPILER=' + CXX],
      cwd=BINARYEN_OUT_DIR)
  proc.check_call(['ninja'], cwd=BINARYEN_OUT_DIR)
  bin_dir = os.path.join(BINARYEN_OUT_DIR, 'bin')
  assert os.path.isdir(bin_dir), 'Expected %s' % bin_dir
  for node in os.listdir(bin_dir):
    f = os.path.join(bin_dir, node)
    if os.path.isfile(f):
      CopyBinaryToArchive(f)
  CopyBinaryToArchive(os.path.join(BINARYEN_SRC_DIR, 'bin', 'wasm.js'))
  js_src_dir = os.path.join(BINARYEN_SRC_DIR, 'src', 'js')
  js_dest_dir = os.path.join(INSTALL_DIR, 'src', 'js')
  print 'copying directory', js_src_dir, 'to', js_dest_dir
  CopyTree(js_src_dir, js_dest_dir)


def Fastcomp():
  buildbot.Step('fastcomp')
  Mkdir(FASTCOMP_OUT_DIR)
  install_dir = os.path.join(INSTALL_DIR, 'fastcomp')
  proc.check_call(
      [PREBUILT_CMAKE_BIN, '-G', 'Ninja', FASTCOMP_SRC_DIR,
       '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
       '-DCMAKE_C_COMPILER=' + CC,
       '-DCMAKE_CXX_COMPILER=' + CXX,
       '-DCMAKE_BUILD_TYPE=Release',
       '-DCMAKE_INSTALL_PREFIX=' + install_dir,
       '-DLLVM_INCLUDE_EXAMPLES=OFF',
       '-DLLVM_BUILD_LLVM_DYLIB=ON',
       '-DLLVM_LINK_LLVM_DYLIB=ON',
       '-DLLVM_INSTALL_TOOLCHAIN_ONLY=ON',
       '-DLLVM_TARGETS_TO_BUILD=X86;JSBackend',
       '-DLLVM_ENABLE_ASSERTIONS=ON'], cwd=FASTCOMP_OUT_DIR)
  proc.check_call(['ninja'], cwd=FASTCOMP_OUT_DIR)
  proc.check_call(['ninja', 'install'], cwd=FASTCOMP_OUT_DIR)
  CopyLLVMTools(FASTCOMP_OUT_DIR, 'fastcomp')


def Emscripten(use_asm=True):
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
      text = config.read().replace('{{WASM_INSTALL}}', INSTALL_DIR)
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
      # Build a C++ file with each active emscripten config. This causes system
      # libs to be built and cached (so we don't have that happen when building
      # tests in parallel). Do it with full debug output.
      # This depends on binaryen already being built and installed into the
      # archive/install dir.
      os.environ['EMCC_DEBUG'] = '2'
      os.environ['EM_CONFIG'] = config
      proc.check_call([
          os.path.join(emscripten_dir, 'em++'),
          os.path.join(EMSCRIPTEN_SRC_DIR, 'tests', 'hello_libcxx.cpp'),
          '-O2', '-s', 'BINARYEN=1', '-s', 'BINARYEN_METHOD="native-wasm"'])

    except proc.CalledProcessError:
      # Note the failure but allow the build to continue.
      buildbot.Fail()
    finally:
      del os.environ['EMCC_DEBUG']
      del os.environ['EM_CONFIG']

  wrapper = os.path.join(SCRIPT_DIR, 'emcc_wrapper.sh')
  shutil.copy2(wrapper, os.path.join(INSTALL_BIN, 'emcc'))
  shutil.copy2(wrapper, os.path.join(INSTALL_BIN, 'em++'))


def Musl():
  buildbot.Step('musl')
  Mkdir(MUSL_OUT_DIR)
  try:
    proc.check_call([
        os.path.join(MUSL_SRC_DIR, 'libc.py'),
        '--clang_dir', INSTALL_BIN,
        '--binaryen_dir', os.path.join(INSTALL_BIN),
        '--sexpr_wasm', os.path.join(INSTALL_BIN, 'wast2wasm'),
        '--musl', MUSL_SRC_DIR], cwd=MUSL_OUT_DIR)
    for f in ['musl.wast', 'musl.wasm']:
      CopyLibraryToArchive(os.path.join(MUSL_OUT_DIR, f))
    CopyLibraryToArchive(os.path.join(MUSL_SRC_DIR,
                                      'arch', 'wasm32', 'wasm.js'))
    CopyTree(os.path.join(MUSL_SRC_DIR, 'include'),
             os.path.join(INSTALL_SYSROOT, 'include'))
    CopyTree(os.path.join(MUSL_SRC_DIR, 'arch', 'wasm32'),
             os.path.join(INSTALL_SYSROOT, 'include'))
  except proc.CalledProcessError:
    # Note the failure but allow the build to continue.
    buildbot.Fail()


def ArchiveBinaries():
  buildbot.Step('Archive binaries')
  # All relevant binaries were copied to the LLVM directory.
  Archive('binaries', Tar(INSTALL_DIR, print_content=True))


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
      Git(['checkout', 'debian/changelog'], cwd=top_dir)
  except proc.CalledProcessError:
    # Note the failure but allow the build to continue.
    buildbot.Fail()
    return

  debfile = os.path.join(os.path.dirname(top_dir),
                         'wasm-toolchain_0.1_amd64.deb')
  UploadFile(debfile, os.path.basename(debfile))


def CompileLLVMTorture():
  name = 'Compile LLVM Torture'
  buildbot.Step(name)
  c = os.path.join(INSTALL_BIN, 'clang')
  cxx = os.path.join(INSTALL_BIN, 'clang++')
  Remove(TORTURE_S_OUT_DIR)
  Mkdir(TORTURE_S_OUT_DIR)
  unexpected_result_count = compile_torture_tests.run(
      c=c, cxx=cxx, testsuite=GCC_TEST_DIR,
      sysroot_dir=INSTALL_SYSROOT,
      fails=LLVM_KNOWN_TORTURE_FAILURES,
      out=TORTURE_S_OUT_DIR)
  Archive('torture-c', Tar(GCC_TEST_DIR))
  Archive('torture-s', Tar(TORTURE_S_OUT_DIR))
  if 0 != unexpected_result_count:
    buildbot.Fail()


def CompileLLVMTortureBinaryen(name, em_config, outdir, fails):
  buildbot.Step('Compile LLVM Torture (%s)' % name)
  os.environ['EM_CONFIG'] = em_config
  c = os.path.join(INSTALL_DIR, 'emscripten', 'emcc')
  cxx = os.path.join(INSTALL_DIR, 'emscripten', 'em++')
  Remove(outdir)
  Mkdir(outdir)
  unexpected_result_count = compile_torture_tests.run(
      c=c, cxx=cxx, testsuite=GCC_TEST_DIR,
      sysroot_dir=INSTALL_SYSROOT,
      fails=fails,
      out=outdir,
      config='binaryen-interpret')
  Archive('torture-' + name, Tar(outdir))
  if 0 != unexpected_result_count:
    buildbot.Fail()
  return outdir


def LinkLLVMTorture(name, linker, fails):
  buildbot.Step('Link LLVM Torture with %s' % name)
  assert os.path.isfile(linker), 'Cannot find linker at %s' % linker
  assembly_files = os.path.join(TORTURE_S_OUT_DIR, '*.s')
  out = os.path.join(WORK_DIR, 'torture-%s' % name)
  Remove(out)
  Mkdir(out)
  unexpected_result_count = link_assembly_files.run(
      linker=linker, files=assembly_files, fails=fails, out=out)
  Archive('torture-%s' % name, Tar(out))
  if 0 != unexpected_result_count:
    buildbot.Fail()
  return out


def AssembleLLVMTorture(name, assembler, indir, fails):
  buildbot.Step('Assemble LLVM Torture with %s' % name)
  assert os.path.isfile(assembler), 'Cannot find assembler at %s' % assembler
  files = os.path.join(indir, '*.wast')
  out = os.path.join(WORK_DIR, 'torture-%s' % name)
  Remove(out)
  Mkdir(out)
  unexpected_result_count = assemble_files.run(
      assembler=assembler,
      files=files,
      fails=fails,
      out=out)
  Archive('torture-%s' % name, Tar(out))
  if 0 != unexpected_result_count:
    buildbot.Fail()
  return out


def ExecuteLLVMTorture(name, runner, indir, fails, extension, outdir='',
                       wasmjs='', extra_files=None, warn_only=False):
  extra_files = [] if extra_files is None else extra_files

  buildbot.Step('Execute LLVM Torture (%s)' % name)
  if not indir:
    print 'Step skipped: no input'
    buildbot.Fail(True)
    return None
  assert os.path.isfile(runner), 'Cannot find runner at %s' % runner
  files = os.path.join(indir, '*.%s' % extension)
  unexpected_result_count = execute_files.run(
      runner=runner,
      files=files,
      fails=fails,
      out=outdir,
      wasmjs=wasmjs,
      extra_files=extra_files)
  if 0 != unexpected_result_count:
      buildbot.Fail(warn_only)
  return outdir


def ExecuteEmscriptenTestSuite(name, config, outdir):
  buildbot.Step('Execute emscripten testsuite (%s)' % name)
  Mkdir(outdir)
  try:
    proc.check_call(
        [sys.executable,
         os.path.join(INSTALL_DIR, 'emscripten', 'tests', 'runner.py'),
         'binaryen2', '--em-config', config],
        cwd=outdir)
  except proc.CalledProcessError:
    buildbot.Fail(True)


class Build(object):
  def __init__(self, name_, runnable_, *args, **kwargs):
    self.name = name_
    self.runnable = runnable_
    self.args = args
    self.kwargs = kwargs

  def Run(self):
    self.runnable(*self.args, **self.kwargs)


def Summary(repos):
  buildbot.Step('Summary')
  info = {'repositories': repos}
  info['build'] = BUILDBOT_BUILDNUMBER
  info['scheduler'] = SCHEDULER
  info_json = json.dumps(info, indent=2)
  print info_json
  print 'Failed steps: %s.' % buildbot.Failed()
  for step in buildbot.FailedList():
    print '    %s' % step

  info_file = os.path.join(INSTALL_DIR, 'buildinfo.json')
  with open(info_file, 'w+') as f:
    f.write(info_json)
    f.write('\n')

  latest_file = '%s/%s' % (BUILDBOT_BUILDERNAME, 'latest.json')
  buildbot.Link('latest.json', cloud.Upload(info_file, latest_file))

  if buildbot.Failed():
    buildbot.Fail()
  else:
    lkgr_file = '%s/%s' % (BUILDBOT_BUILDERNAME, 'lkgr.json')
    buildbot.Link('lkgr.json', cloud.Upload(info_file, lkgr_file))


def AllBuilds(use_asm=False):
  return [
      # Host tools
      Build('llvm', LLVM),
      Build('v8', V8),
      Build('wabt', Wabt),
      Build('ocaml', OCaml),
      Build('spec', Spec),
      Build('binaryen', Binaryen),
      Build('fastcomp', Fastcomp),
      Build('emscripten', Emscripten, use_asm),
      # Target libs
      Build('musl', Musl),
      # Archive
      Build('archive', ArchiveBinaries),
      Build('debian', DebianPackage),
  ]


def BuildRepos(filter, use_asm=False):
  for rule in filter.Apply(AllBuilds(use_asm)):
    rule.Run()


class Test(object):
  def __init__(self, name_, runnable_):
    self.name = name_
    self.runnable = runnable_

  def Test(self):
    self.runnable()


def TestBare():
  CompileLLVMTorture()
  s2wasm_out = LinkLLVMTorture(
      name='s2wasm',
      linker=os.path.join(INSTALL_BIN, 's2wasm'),
      fails=S2WASM_KNOWN_TORTURE_FAILURES)
  wast2wasm_out = AssembleLLVMTorture(
      name='wast2wasm',
      assembler=os.path.join(INSTALL_BIN, 'wast2wasm'),
      indir=s2wasm_out,
      fails=WAST2WASM_KNOWN_TORTURE_FAILURES)
  ExecuteLLVMTorture(
      name='wasm-shell',
      runner=os.path.join(INSTALL_BIN, 'wasm-shell'),
      indir=s2wasm_out,
      fails=BINARYEN_SHELL_KNOWN_TORTURE_FAILURES,
      extension='wast',
      warn_only=True)  # TODO wasm-shell is flaky when running tests.
  ExecuteLLVMTorture(
      name='spec',
      runner=os.path.join(INSTALL_BIN, 'wasm.opt'),
      indir=s2wasm_out,
      fails=SPEC_KNOWN_TORTURE_FAILURES,
      warn_only=True,  # TODO https://github.com/WebAssembly/spec/issues/353
      extension='wast')
  ExecuteLLVMTorture(
      name='d8',
      runner=os.path.join(INSTALL_BIN, 'd8'),
      indir=wast2wasm_out,
      fails=V8_KNOWN_TORTURE_FAILURES,
      extension='wasm',
      warn_only=True,
      wasmjs=os.path.join(INSTALL_LIB, 'wasm.js'))
  ExecuteLLVMTorture(
      name='d8-musl',
      runner=os.path.join(INSTALL_BIN, 'd8'),
      indir=wast2wasm_out,
      fails=V8_MUSL_KNOWN_TORTURE_FAILURES,
      extension='wasm',
      warn_only=True,
      wasmjs=os.path.join(INSTALL_LIB, 'wasm.js'),
      extra_files=[os.path.join(INSTALL_LIB, 'musl.wasm')])


def TestAsm():
  asm2wasm_out = CompileLLVMTortureBinaryen(
      'asm2wasm',
      EMSCRIPTEN_CONFIG_ASMJS,
      ASM2WASM_TORTURE_OUT_DIR,
      ASM2WASM_KNOWN_TORTURE_COMPILE_FAILURES)
  ExecuteLLVMTorture(
      name='asm2wasm',
      runner=os.path.join(INSTALL_BIN, 'd8'),
      indir=asm2wasm_out,
      fails=ASM2WASM_KNOWN_TORTURE_FAILURES,
      extension='c.js',
      outdir=asm2wasm_out)  # emscripten's wasm.js expects all files in cwd.


def TestEmwasm():
  emscripten_wasm_out = CompileLLVMTortureBinaryen(
      'emwasm',
      EMSCRIPTEN_CONFIG_WASM,
      EMSCRIPTENWASM_TORTURE_OUT_DIR,
      EMSCRIPTENWASM_KNOWN_TORTURE_COMPILE_FAILURES)
  ExecuteLLVMTorture(
      name='emwasm',
      runner=os.path.join(INSTALL_BIN, 'd8'),
      indir=emscripten_wasm_out,
      fails=EMSCRIPTENWASM_KNOWN_TORTURE_FAILURES,
      extension='c.js',
      outdir=emscripten_wasm_out)


def TestEmtest():
  ExecuteEmscriptenTestSuite(
      'emtest',
      EMSCRIPTEN_CONFIG_WASM,
      EMSCRIPTEN_TEST_OUT_DIR)


ALL_TESTS = [
    Test('bare', TestBare),
    Test('asm', TestAsm),
    Test('emwasm', TestEmwasm),
    Test('emtest', TestEmtest),
]


def TextWrapNameList(prefix, items):
  import textwrap
  width = 80  # TODO(binji): better guess?
  names = sorted(item.name for item in items)
  return '%s%s' % (prefix, textwrap.fill(' '.join(names), width,
                                         initial_indent='  ',
                                         subsequent_indent='  '))


def ParseArgs():
  import argparse

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
      '--git-status', dest='git_status', default=False, action='store_true',
      help='Show git status for each sync target. '
           "Doesn't sync, build, or test")

  return parser.parse_args()


def run(sync_filter, build_filter, test_filter, options):
  if options.git_status:
    for s in ALL_SOURCES:
      s.PrintGitStatus()
    return 0

  Clobber()
  Chdir(SCRIPT_DIR)
  Mkdir(WORK_DIR)
  SyncRepos(sync_filter, options.sync_lkgr)
  repos = GetRepoInfo()
  if build_filter.All():
    Remove(INSTALL_DIR)
    Mkdir(INSTALL_DIR)
    Mkdir(INSTALL_BIN)
    Mkdir(INSTALL_LIB)

  # Add prebuilt cmake to PATH so any subprocesses use a consistent cmake.
  os.environ['PATH'] = (os.path.join(PREBUILT_CMAKE_DIR, 'bin') +
                        os.pathsep + os.environ['PATH'])

  try:
    BuildRepos(build_filter, test_filter.Check('asm'))
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
  import time
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
    ret = run(sync_filter, build_filter, test_filter, options)
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
