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

import glob
import json
import multiprocessing
import os
import shutil
import sys
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
LLVM_TEST_SUITE_SRC_DIR = os.path.join(WORK_DIR, 'llvm-test-suite')

EMSCRIPTEN_SRC_DIR = os.path.join(WORK_DIR, 'emscripten')
FASTCOMP_SRC_DIR = os.path.join(WORK_DIR, 'emscripten-fastcomp')

GCC_SRC_DIR = os.path.join(WORK_DIR, 'gcc')
GCC_TEST_DIR = os.path.join(GCC_SRC_DIR, 'gcc', 'testsuite')

V8_SRC_DIR = os.path.join(WORK_DIR, 'v8', 'v8')
os.environ['GYP_GENERATORS'] = 'ninja'  # Used to build V8.

SEXPR_SRC_DIR = os.path.join(WORK_DIR, 'sexpr-wasm-prototype')

SPEC_SRC_DIR = os.path.join(WORK_DIR, 'spec')
ML_DIR = os.path.join(SPEC_SRC_DIR, 'ml-proto')
BINARYEN_SRC_DIR = os.path.join(WORK_DIR, 'binaryen')
MUSL_SRC_DIR = os.path.join(WORK_DIR, 'musl')

PREBUILT_CLANG = os.path.join(WORK_DIR, 'chromium-clang')
PREBUILT_CLANG_TOOLS_CLANG = os.path.join(PREBUILT_CLANG, 'tools', 'clang')
PREBUILT_CLANG_BIN = os.path.join(
    PREBUILT_CLANG, 'third_party', 'llvm-build', 'Release+Asserts', 'bin')
CC = os.path.join(PREBUILT_CLANG_BIN, 'clang')
CXX = os.path.join(PREBUILT_CLANG_BIN, 'clang++')

LLVM_OUT_DIR = os.path.join(WORK_DIR, 'llvm-out')
V8_OUT_DIR = os.path.join(V8_SRC_DIR, 'out', 'Release')
SEXPR_OUT_DIR = os.path.join(SEXPR_SRC_DIR, 'out')
BINARYEN_OUT_DIR = os.path.join(WORK_DIR, 'binaryen-out')
BINARYEN_BIN_DIR = os.path.join(BINARYEN_OUT_DIR, 'bin')
FASTCOMP_OUT_DIR = os.path.join(WORK_DIR, 'fastcomp-out')
MUSL_OUT_DIR = os.path.join(WORK_DIR, 'musl-out')
TORTURE_S_OUT_DIR = os.path.join(WORK_DIR, 'torture-s')

INSTALL_DIR = os.path.join(WORK_DIR, 'wasm-install')
INSTALL_BIN = os.path.join(INSTALL_DIR, 'bin')
INSTALL_LIB = os.path.join(INSTALL_DIR, 'lib')

# Avoid flakes: use cached repositories to avoid relying on external network.
GITHUB_REMOTE = 'github'
GITHUB_SSH = 'git@github.com:'
GIT_MIRROR_BASE = 'https://chromium.googlesource.com/'
LLVM_MIRROR_BASE = GIT_MIRROR_BASE + 'external/llvm.org/'
GITHUB_MIRROR_BASE = GIT_MIRROR_BASE + 'external/github.com/'
WASM_GIT_BASE = GITHUB_MIRROR_BASE + 'WebAssembly/'
EMSCRIPTEN_GIT_BASE = GITHUB_MIRROR_BASE + 'kripken/'

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
V8_KNOWN_TORTURE_FAILURES = os.path.join(SCRIPT_DIR, 'test',
                                         'd8_' + IT_IS_KNOWN)
V8_MUSL_KNOWN_TORTURE_FAILURES = os.path.join(SCRIPT_DIR, 'test',
                                              'd8_musl_' + IT_IS_KNOWN)
SEXPR_S2WASM_KNOWN_TORTURE_FAILURES = os.path.join(SEXPR_SRC_DIR, 's2wasm_' +
                                                   IT_IS_KNOWN)
SPEC_KNOWN_TORTURE_FAILURES = os.path.join(SCRIPT_DIR, 'test',
                                           'spec_' + IT_IS_KNOWN)
S2WASM_KNOWN_TORTURE_FAILURES = os.path.join(BINARYEN_SRC_DIR, 'test',
                                             's2wasm_' + IT_IS_KNOWN)
BINARYEN_SHELL_KNOWN_TORTURE_FAILURES = (
    os.path.join(BINARYEN_SRC_DIR, 'test',
                 's2wasm_known_binaryen_shell_test_failures.txt'))


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

# Pin the GCC revision so that new torture tests don't break the bot. This
# should be manually updated when convenient.
GCC_REVISION = 'b6125c702850488ac3bfb1079ae5c9db89989406'
GCC_CLONE_DEPTH = 1000


# Shell utilities

def Chdir(path):
  print 'Change directory to: %s' % path
  os.chdir(path)


def Mkdir(path):
  if os.path.exists(path):
    if not os.path.isdir(path):
      raise Exception('Path %s is not a directory!' % path)
    print 'Directory %s already exists' % path
  else:
    os.mkdir(path)


def Remove(path):
  """Remove file or directory if it exists, do nothing otherwise."""
  if os.path.exists(path):
    print 'Removing %s' % path
    if os.path.isdir(path):
      shutil.rmtree(path)
    else:
      os.remove(path)


def CopyBinaryToArchive(binary):
  """All binaries are archived in the same tar file."""
  print 'Copying binary %s to archive %s' % (binary, INSTALL_BIN)
  shutil.copy2(binary, INSTALL_BIN)


def CopyLibraryToArchive(library):
  """All libraries are archived in the same tar file."""
  print 'Copying library %s to archive %s' % (library, INSTALL_LIB)
  shutil.copy2(library, INSTALL_LIB)


def Tar(directory, print_content=False):
  """Create a tar file from directory."""
  if not os.environ.get('BUILDBOT_BUILDERNAME'):
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


def Archive(name, tar):
  """Archive the tar file with the given name, and with the LLVM git hash."""
  if not os.environ.get('BUILDBOT_BUILDERNAME'):
    return
  git_gs = 'git/wasm-%s-%s.tbz2' % (name, BUILDBOT_BUILDNUMBER)
  buildbot.Link('download', cloud.Upload(tar, git_gs))


# Repo and subproject utilities

def GitRemoteUrl(cwd, remote):
  """Get the URL of a remote."""
  return proc.check_output(['git', 'config', '--get', 'remote.%s.url' %
                            remote], cwd=cwd).strip()


def HasRemote(cwd, remote):
  """"Checked whether the named remote exists."""
  remotes = proc.check_output(['git', 'remote'],
                              cwd=cwd).strip().splitlines()
  return remote in remotes


def AddGithubRemote(cwd):
  """When using the cloned repository for development, it's useful to have a
  remote to github because origin points at a cache which is read-only."""
  origin_url = GitRemoteUrl(cwd, 'origin')
  if WASM_GIT_BASE not in origin_url:
    print '%s not a github mirror' % cwd
    return
  if HasRemote(cwd, GITHUB_REMOTE):
    print '%s has %s as its "%s" remote' % (
        cwd, GitRemoteUrl(cwd, GITHUB_REMOTE), GITHUB_REMOTE)
    return
  remote = GITHUB_SSH + '/'.join(GitRemoteUrl(cwd, 'origin').split('/')[-2:])
  print '%s has no github remote, adding %s' % (cwd, remote)
  proc.check_call(['git', 'remote', 'add', GITHUB_REMOTE, remote],
                  cwd=cwd)


def GitConfigRebaseMaster(cwd):
  """Avoid generating a non-linear history in the clone

  The upstream repository is in Subversion. Use `git pull --rebase` instead of
  git pull: llvm.org/docs/GettingStarted.html#git-mirror
  """
  proc.check_call(
      ['git', 'config', 'branch.master.rebase', 'true'], cwd=cwd)


class Source:
  """Metadata about a sync-able source repo on the waterfall"""
  def __init__(self, name, src_dir, git_repo, checkout='origin/master',
               depth=None, custom_sync=None):
    self.name = name
    self.src_dir = src_dir
    self.git_repo = git_repo
    self.checkout = checkout
    self.depth = depth
    self.custom_sync = custom_sync

  def Sync(self):
    if self.custom_sync:
      self.custom_sync(self.name, self.src_dir, self.git_repo)
    else:
      self.GitCloneFetchCheckout()

  def GitCloneFetchCheckout(self):
    """Clone a git repo if not already cloned, then fetch and checkout."""
    if os.path.isdir(self.src_dir):
      print '%s directory already exists' % self.name
    else:
      clone = ['git', 'clone', self.git_repo, self.src_dir]
      if self.depth:
        clone.append('--depth')
        clone.append(str(self.depth))
      proc.check_call(clone)
    proc.check_call(['git', 'fetch'], cwd=self.src_dir)
    if not self.checkout.startswith('origin/'):
      sys.stderr.write(('WARNING: `git checkout %s` not based on origin, '
                        'checking out local branch' % self.checkout))
    proc.check_call(['git', 'checkout', self.checkout], cwd=self.src_dir)
    AddGithubRemote(self.src_dir)

  def CurrentGitInfo(self):
    def pretty(fmt):
      return proc.check_output(
          ['git', 'log', '-n1', '--pretty=format:%s' % fmt],
          cwd=self.src_dir).strip()
    remote = proc.check_output(['git', 'config', '--get', 'remote.origin.url'],
                               cwd=self.src_dir).strip()
    return {
        'hash': pretty('%H'),
        'name': pretty('%aN'),
        'email': pretty('%ae'),
        'subject': pretty('%s'),
        'remote': remote,
    }


def ChromiumFetchSync(name, work_dir, git_repo, checkout='origin/master'):
  """Some Chromium projects want to use gclient for clone and dependencies."""
  if os.path.isdir(work_dir):
    print '%s directory already exists' % name
  else:
    # Create Chromium repositories one deeper, separating .gclient files.
    parent = os.path.split(work_dir)[0]
    Mkdir(parent)
    proc.check_call(['gclient', 'config', git_repo], cwd=parent)
    proc.check_call(['git', 'clone', git_repo], cwd=parent)
  proc.check_call(['git', 'fetch'], cwd=work_dir)
  proc.check_call(['git', 'checkout', checkout], cwd=work_dir)
  proc.check_call(['gclient', 'sync'], cwd=work_dir)
  return (name, work_dir)


def SyncPrebuiltClang(name, src_dir, git_repo):
  tools_clang = os.path.join(src_dir, 'tools', 'clang')
  if os.path.isdir(tools_clang):
    print 'Prebuilt Chromium Clang directory already exists'
  else:
    print 'Cloning Prebuilt Chromium Clang directory'
    Mkdir(src_dir)
    Mkdir(os.path.join(src_dir, 'tools'))
    proc.check_call(
        ['git', 'clone', git_repo, tools_clang])
  proc.check_call(['git', 'fetch'], cwd=tools_clang)
  proc.check_call(
      [os.path.join(tools_clang, 'scripts', 'update.py')])
  assert os.path.isfile(CC), 'Expect clang at %s' % CC
  assert os.path.isfile(CXX), 'Expect clang++ at %s' % CXX
  return ('chromium-clang', tools_clang)


def NoSync(*args):
  pass

ALL_SOURCES = [
    Source('waterfall', SCRIPT_DIR, None, custom_sync=NoSync),
    Source('llvm', LLVM_SRC_DIR,
           LLVM_MIRROR_BASE + 'llvm'),
    Source('clang', CLANG_SRC_DIR,
           LLVM_MIRROR_BASE + 'clang'),
    Source('llvm-test-suite', LLVM_TEST_SUITE_SRC_DIR,
           LLVM_MIRROR_BASE + 'test-suite'),
    Source('emscripten', EMSCRIPTEN_SRC_DIR,
           EMSCRIPTEN_GIT_BASE + 'emscripten'),
    Source('fastcomp', FASTCOMP_SRC_DIR,
           EMSCRIPTEN_GIT_BASE + 'emscripten-fastcomp'),
    Source('fastcomp-clang',
           os.path.join(FASTCOMP_SRC_DIR, 'tools', 'clang'),
           EMSCRIPTEN_GIT_BASE + 'emscripten-fastcomp-clang'),
    Source('gcc', GCC_SRC_DIR,
           GIT_MIRROR_BASE + 'chromiumos/third_party/gcc',
           checkout=GCC_REVISION, depth=GCC_CLONE_DEPTH),
    Source('v8', V8_SRC_DIR,
           GIT_MIRROR_BASE + 'v8/v8',
           custom_sync=ChromiumFetchSync),
    Source('chromium-clang', PREBUILT_CLANG,
           GIT_MIRROR_BASE + 'chromium/src/tools/clang',
           custom_sync=SyncPrebuiltClang),
    Source('sexpr', SEXPR_SRC_DIR,
           WASM_GIT_BASE + 'sexpr-wasm-prototype.git'),
    Source('spec', SPEC_SRC_DIR,
           WASM_GIT_BASE + 'spec.git'),
    Source('binaryen', BINARYEN_SRC_DIR,
           WASM_GIT_BASE + 'binaryen.git'),
    Source('musl', MUSL_SRC_DIR,
           WASM_GIT_BASE + 'musl.git',
           checkout='origin/wasm-prototype-1')
]


def CurrentSvnRev(path):
  return int(proc.check_output(
      ['git', 'svn', 'find-rev', 'HEAD'], cwd=path).strip())


def FindPriorSvnRev(path, goal):
  revs = proc.check_output(
      ['git', 'rev-list', 'origin/master'], cwd=path).splitlines()
  for rev in revs:
    num = proc.check_output(
        ['git', 'svn', 'find-rev', rev], cwd=path).strip()
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
    proc.check_call(['git', 'checkout', prior_rev], cwd=secondary)


def SyncLLVMClang():
  llvm_rev = BUILDBOT_REVISION if SCHEDULER == 'llvm' else 'origin/master'
  clang_rev = BUILDBOT_REVISION if SCHEDULER == 'clang' else 'origin/master'
  proc.check_call(['git', 'checkout', llvm_rev], cwd=LLVM_SRC_DIR)
  proc.check_call(['git', 'checkout', clang_rev], cwd=CLANG_SRC_DIR)
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


class Filter:
  """Filter for source or build rules, to allow including or excluding only
     selected targets.
  """
  def __init__(self, include=None, exclude=None):
    """ include:
         if present, only items in it will be included (if empty, nothing will
         be included).
        exclude:
         if present, items in it will be excluded.
        include ane exclude cannot both be present.
    """
    if include and exclude:
      raise Exception('Filter cannot include both include and exclude rules')

    self.include = include
    self.exclude = exclude

  def Apply(self, targets):
    """ Return the filtered list of targets. """
    if self.include is not None:
      return [t for t in targets if t.name in self.include]
    if self.exclude:
      return [t for t in targets if t.name not in self.exclude]
    return targets

  class DummyTarget:
    def __init__(self, name):
      self.name = name

  def Check(self, target):
    """ Return true if the specified target will be run. """
    return len(self.Apply([self.DummyTarget(target)])) > 0

  def All(self):
    """ Return true if all possible targets will be run. """
    return self.include is None and not self.exclude


def SyncRepos(filter=None):
  buildbot.Step('Sync Repos')
  if not filter:
    filter = Filter()
  # TODO Remove this when sexpr-wasm-prototype/issues/35 is fixed.
  if filter.Check('sexpr'):
    Remove(SEXPR_SRC_DIR)
  for repo in filter.Apply(ALL_SOURCES):
    repo.Sync()
  # Special cases
  if filter.Check('clang'):
    SyncLLVMClang()
  if filter.Check('ocaml'):
    SyncOCaml()


def GetRepoInfo():
  """Collect a readable form of all repo information here, preventing the
  summary from getting out of sync with the actual list of repos."""
  info = {}
  for r in ALL_SOURCES:
    info[r.name] = r.CurrentGitInfo()
  return info


def LLVM():
  buildbot.Step('LLVM')
  Mkdir(LLVM_OUT_DIR)
  proc.check_call(
      ['cmake', '-G', 'Ninja', LLVM_SRC_DIR,
       '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
       '-DLLVM_BUILD_TESTS=ON',
       '-DCMAKE_C_COMPILER=' + CC,
       '-DCMAKE_CXX_COMPILER=' + CXX,
       '-DCMAKE_BUILD_TYPE=Release',
       '-DCMAKE_INSTALL_PREFIX=' + INSTALL_DIR,
       '-DLLVM_INCLUDE_EXAMPLES=OFF',
       '-DCLANG_INCLUDE_EXAMPLES=OFF',
       '-DLLVM_BUILD_LLVM_DYLIB=ON',
       '-DLLVM_LINK_LLVM_DYLIB=ON',
       '-DLLVM_INSTALL_TOOLCHAIN_ONLY=ON',
       '-DLLVM_ENABLE_ASSERTIONS=ON',
       '-DLLVM_EXPERIMENTAL_TARGETS_TO_BUILD=WebAssembly',
       '-DLLVM_TARGETS_TO_BUILD=X86'], cwd=LLVM_OUT_DIR)
  proc.check_call(['ninja'], cwd=LLVM_OUT_DIR)
  proc.check_call(['ninja', 'check-all'], cwd=LLVM_OUT_DIR)
  proc.check_call(['ninja', 'install'], cwd=LLVM_OUT_DIR)
  # The following isn't useful for now, and takes up space.
  Remove(os.path.join(INSTALL_BIN, 'clang-check'))
  # The following are useful, LLVM_INSTALL_TOOLCHAIN_ONLY did away with them.
  extra_bins = ['FileCheck', 'lli', 'llc', 'llvm-as', 'llvm-dis', 'llvm-link',
                'llvm-nm', 'opt']
  extra_libs = ['libLLVM*.so']
  for p in [glob.glob(os.path.join(LLVM_OUT_DIR, 'bin', b)) for b in
            extra_bins]:
    for e in p:
      CopyBinaryToArchive(os.path.join(LLVM_OUT_DIR, 'bin', e))
  for p in [glob.glob(os.path.join(LLVM_OUT_DIR, 'lib', l)) for l in
            extra_libs]:
    for e in p:
      CopyLibraryToArchive(os.path.join(LLVM_OUT_DIR, 'lib', e))


def V8():
  buildbot.Step('V8')
  proc.check_call(['ninja', '-C', V8_OUT_DIR, 'd8', 'unittests'],
                  cwd=V8_SRC_DIR)
  proc.check_call(['tools/run-tests.py', 'unittests', '--no-presubmit',
                   '--shell-dir', V8_OUT_DIR],
                  cwd=V8_SRC_DIR)
  to_archive = ['d8', 'natives_blob.bin', 'snapshot_blob.bin']
  for a in to_archive:
    CopyBinaryToArchive(os.path.join(V8_OUT_DIR, a))


def Sexpr():
  buildbot.Step('Sexpr')
  # sexpr-wasm builds in its own in-tree out/ folder. The build is fast, so
  # always clobber.
  proc.check_call(['make', 'clean'], cwd=SEXPR_SRC_DIR)
  proc.check_call(['make',
                   'CC=%s' % CC,
                   'CXX=%s' % CXX],
                  cwd=SEXPR_SRC_DIR)
  sexpr = os.path.join(SEXPR_OUT_DIR, 'sexpr-wasm')
  CopyBinaryToArchive(sexpr)


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
      ['cmake', '-G', 'Ninja', BINARYEN_SRC_DIR,
       '-DCMAKE_C_COMPILER=' + CC,
       '-DCMAKE_CXX_COMPILER=' + CXX],
      cwd=BINARYEN_OUT_DIR)
  proc.check_call(['ninja'], cwd=BINARYEN_OUT_DIR)
  assert os.path.isdir(BINARYEN_BIN_DIR), 'Expected %s' % BINARYEN_BIN_DIR
  for node in os.listdir(BINARYEN_BIN_DIR):
    f = os.path.join(BINARYEN_BIN_DIR, node)
    if os.path.isfile(f):
      CopyBinaryToArchive(f)


def Fastcomp():
  buildbot.Step('fastcomp')
  Mkdir(FASTCOMP_OUT_DIR)
  proc.check_call(
      ['cmake', '-G', 'Ninja', FASTCOMP_SRC_DIR,
       '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
       '-DCMAKE_C_COMPILER=' + CC,
       '-DCMAKE_CXX_COMPILER=' + CXX,
       '-DCMAKE_BUILD_TYPE=Release',
       '-DCMAKE_INSTALL_PREFIX=' + os.path.join(INSTALL_DIR, 'fastcomp'),
       '-DLLVM_INCLUDE_EXAMPLES=OFF',
       '-DCLANG_INCLUDE_EXAMPLES=OFF',
       '-DLLVM_BUILD_LLVM_DYLIB=ON',
       '-DLLVM_LINK_LLVM_DYLIB=ON',
       '-DLLVM_TARGETS_TO_BUILD=X86;JSBackend',
       '-DLLVM_ENABLE_ASSERTIONS=ON'], cwd=FASTCOMP_OUT_DIR)
  proc.check_call(['ninja'], cwd=FASTCOMP_OUT_DIR)
  try:
    proc.check_call(['ninja', 'check'], cwd=FASTCOMP_OUT_DIR)
  except proc.CalledProcessError:
    print 'ಠ_ಠ'
  proc.check_call(['ninja', 'install'], cwd=FASTCOMP_OUT_DIR)


def Emscripten():
  buildbot.Step('emscripten')
  os.environ['EMSCRIPTEN'] = EMSCRIPTEN_SRC_DIR
  os.environ['LLVM'] = os.path.join(INSTALL_DIR, 'fastcomp', 'bin')
  os.environ['V8'] = os.path.join(INSTALL_DIR, 'bin', 'd8')
  em_config = os.path.join(INSTALL_DIR, 'emscripten.conf')
  shutil.copy2(os.path.join(SCRIPT_DIR, 'emscripten_config.py'),
               os.path.join(em_config))
  proc.check_call([os.path.join(EMSCRIPTEN_SRC_DIR, 'emcc'),
                   '--em-config', em_config,
                   os.path.join(EMSCRIPTEN_SRC_DIR, 'tests', 'hello_world.cpp')])

def Musl():
  buildbot.Step('musl')
  Mkdir(MUSL_OUT_DIR)
  try:
    proc.check_call([
        os.path.join(MUSL_SRC_DIR, 'libc.py'),
        '--clang_dir', INSTALL_BIN,
        '--binaryen_dir', INSTALL_BIN,
        '--sexpr_wasm', os.path.join(INSTALL_BIN, 'sexpr-wasm'),
        '--musl', MUSL_SRC_DIR], cwd=MUSL_OUT_DIR)
    for f in ['musl.wast', 'musl.wasm']:
      CopyLibraryToArchive(os.path.join(MUSL_OUT_DIR, f))
    CopyLibraryToArchive(os.path.join(MUSL_SRC_DIR,
                                      'arch', 'wasm32', 'wasm.js'))
  except proc.CalledProcessError:
    buildbot.Fail()


def ArchiveBinaries():
  buildbot.Step('Archive binaries')
  # All relevant binaries were copied to the LLVM directory.
  Archive('binaries', Tar(INSTALL_DIR, print_content=True))


def CompileLLVMTorture():
  name = 'Compile LLVM Torture'
  buildbot.Step(name)
  c = os.path.join(INSTALL_BIN, 'clang')
  cxx = os.path.join(INSTALL_BIN, 'clang++')
  Remove(TORTURE_S_OUT_DIR)
  Mkdir(TORTURE_S_OUT_DIR)
  unexpected_result_count = compile_torture_tests.run(
      c=c, cxx=cxx, testsuite=GCC_TEST_DIR,
      fails=LLVM_KNOWN_TORTURE_FAILURES,
      out=TORTURE_S_OUT_DIR)
  Archive('torture-c', Tar(GCC_TEST_DIR))
  Archive('torture-s', Tar(TORTURE_S_OUT_DIR))
  if 0 != unexpected_result_count:
    buildbot.Fail()


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


def ExecuteLLVMTorture(name, runner, indir, fails, extension, has_output,
                       wasmjs='', extra_files=[], is_flaky=False):
  buildbot.Step('Execute LLVM Torture with %s' % name)
  assert os.path.isfile(runner), 'Cannot find runner at %s' % runner
  files = os.path.join(indir, '*.%s' % extension)
  out = os.path.join(WORK_DIR, 'torture-%s' % name) if has_output else ''
  if has_output:
    Remove(out)
    Mkdir(out)
  unexpected_result_count = execute_files.run(
      runner=runner,
      files=files,
      fails=fails,
      out=out,
      wasmjs=wasmjs,
      extra_files=extra_files)
  if has_output:
    Archive('torture-%s' % name, Tar(out))
  if 0 != unexpected_result_count:
      buildbot.Fail(is_flaky)
  return out


class Build:
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
  info_json = json.dumps(info)
  print info
  print 'Failed steps: %s.' % buildbot.Failed()
  with open('latest', 'w+') as f:
    f.write(info_json)
  buildbot.Link('latest', cloud.Upload('latest', 'git/latest'))
  if buildbot.Failed():
    buildbot.Fail()
  else:
    with open('lkgr', 'w+') as f:
      f.write(info_json)
    buildbot.Link('lkgr', cloud.Upload('lkgr', 'git/lkgr'))


ALL_BUILDS = [
    # Host tools
    Build('llvm', LLVM),
    Build('v8', V8),
    Build('sexpr', Sexpr),
    Build('ocaml', OCaml),
    Build('spec', Spec),
    Build('binaryen', Binaryen),
    Build('fastcomp', Fastcomp),
    Build('emscripten', Emscripten),
    # Target libs
    Build('musl', Musl),
    # Archive
    Build('archive', ArchiveBinaries),
]


def BuildRepos(filter=None):
  if not filter:
    filter = Filter()
  for rule in filter.Apply(ALL_BUILDS):
    rule.Run()


def ParseArgs():
  import argparse

  def SplitComma(arg):
    if not arg:
      return None
    return arg.split(',')

  parser = argparse.ArgumentParser(
      description='Wasm waterfall top-level CI script')
  sync_grp = parser.add_mutually_exclusive_group()
  sync_grp.add_argument('--no-sync', dest='sync',
                        default=True, action='store_false',
                        help='Skip fetching and checking out source repos')
  sync_grp.add_argument(
      '--sync-include', dest='sync_include', default='', type=SplitComma,
      help='Include only the comma-separated list of sync targets')
  sync_grp.add_argument(
      '--sync-exclude', dest='sync_exclude', default='', type=SplitComma,
      help='Include only the comma-separated list of sync targets')

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
  return parser.parse_args()


def main(sync_filter, build_filter):
  Clobber()
  Chdir(SCRIPT_DIR)
  Mkdir(WORK_DIR)
  if sync_filter.Check(''):
    repos = GetRepoInfo()
  SyncRepos(sync_filter)
  if build_filter.All():
    Remove(INSTALL_DIR)
    Mkdir(INSTALL_DIR)
    Mkdir(INSTALL_BIN)
    Mkdir(INSTALL_LIB)
  BuildRepos(build_filter)
  sys.exit(0)
  CompileLLVMTorture()
  s2wasm_out = LinkLLVMTorture(
      name='s2wasm',
      linker=os.path.join(INSTALL_BIN, 's2wasm'),
      fails=S2WASM_KNOWN_TORTURE_FAILURES)
  sexpr_wasm_out = AssembleLLVMTorture(
      name='s2wasm-sexpr-wasm',
      assembler=os.path.join(INSTALL_BIN, 'sexpr-wasm'),
      indir=s2wasm_out,
      fails=SEXPR_S2WASM_KNOWN_TORTURE_FAILURES)
  ExecuteLLVMTorture(
      name='binaryen-shell',
      runner=os.path.join(INSTALL_BIN, 'binaryen-shell'),
      indir=s2wasm_out,
      fails=BINARYEN_SHELL_KNOWN_TORTURE_FAILURES,
      extension='wast',
      has_output=False,
      is_flaky=True)  # TODO binaryen-shell is flaky when running tests.
  ExecuteLLVMTorture(
      name='spec',
      runner=os.path.join(INSTALL_BIN, 'wasm.opt'),
      indir=s2wasm_out,
      fails=SPEC_KNOWN_TORTURE_FAILURES,
      extension='wast',
      has_output=False)
  ExecuteLLVMTorture(
      name='d8',
      runner=os.path.join(INSTALL_BIN, 'd8'),
      indir=sexpr_wasm_out,
      fails=V8_KNOWN_TORTURE_FAILURES,
      extension='wasm',
      has_output=False,
      wasmjs=os.path.join(INSTALL_LIB, 'wasm.js'))
  ExecuteLLVMTorture(
      name='d8-musl',
      runner=os.path.join(INSTALL_BIN, 'd8'),
      indir=sexpr_wasm_out,
      fails=V8_MUSL_KNOWN_TORTURE_FAILURES,
      extension='wasm',
      has_output=False,
      wasmjs=os.path.join(INSTALL_LIB, 'wasm.js'),
      extra_files=[os.path.join(INSTALL_LIB, 'musl.wasm')])
  # Keep the summary step last: it'll be marked as red if the return code is
  # non-zero. Individual steps are marked as red with buildbot.Fail().
  Summary(repos)
  return buildbot.Failed()


if __name__ == '__main__':
  options = ParseArgs()
  sync_include = options.sync_include if options.sync else []
  sync_filter = Filter(sync_include, options.sync_exclude)
  build_include = options.build_include if options.build else []
  build_filter = Filter(build_include, options.build_exclude)
  sys.exit(main(sync_filter, build_filter))
