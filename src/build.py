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
import json
import multiprocessing
import os
import shutil
import sys
import urllib2

import assemble_files
import compile_torture_tests
import execute_files
import link_assembly_files
import proc


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.path.join(SCRIPT_DIR, 'work')

CLOUD_STORAGE_BASE_URL = 'https://storage.googleapis.com/'
CLOUD_STORAGE_PATH = 'wasm-llvm/builds/'

IT_IS_KNOWN = 'known_gcc_test_failures.txt'

WASMJS = os.path.join(SCRIPT_DIR, 'test', 'wasm.js')

LLVM_SRC_DIR = os.path.join(WORK_DIR, 'llvm')
CLANG_SRC_DIR = os.path.join(LLVM_SRC_DIR, 'tools', 'clang')
LLVM_KNOWN_TORTURE_FAILURES = os.path.join(LLVM_SRC_DIR, 'lib', 'Target',
                                           'WebAssembly', IT_IS_KNOWN)

GCC_SRC_DIR = os.path.join(WORK_DIR, 'gcc')
GCC_TEST_DIR = os.path.join(GCC_SRC_DIR, 'gcc', 'testsuite')

V8_SRC_DIR = os.path.join(WORK_DIR, 'v8', 'v8')
V8_KNOWN_TORTURE_FAILURES = os.path.join(SCRIPT_DIR, 'test',
                                         'd8_' + IT_IS_KNOWN)
os.environ['GYP_GENERATORS'] = 'ninja'  # Used to build V8.

SEXPR_SRC_DIR = os.path.join(WORK_DIR, 'sexpr-wasm-prototype')
SEXPR_S2WASM_KNOWN_TORTURE_FAILURES = os.path.join(SEXPR_SRC_DIR, 's2wasm_' +
                                                   IT_IS_KNOWN)

SPEC_SRC_DIR = os.path.join(WORK_DIR, 'spec')
ML_DIR = os.path.join(SPEC_SRC_DIR, 'ml-proto')
BINARYEN_SRC_DIR = os.path.join(WORK_DIR, 'binaryen')
S2WASM_KNOWN_TORTURE_FAILURES = os.path.join(BINARYEN_SRC_DIR, 'test',
                                             's2wasm_' + IT_IS_KNOWN)
BINARYEN_SHELL_KNOWN_TORTURE_FAILURES = (
    os.path.join(BINARYEN_SRC_DIR, 'test',
                 's2wasm_known_binaryen_shell_test_failures.txt'))

PREBUILT_CLANG = os.path.join(WORK_DIR, 'chromium-clang')
PREBUILT_CLANG_TOOLS = os.path.join(PREBUILT_CLANG, 'tools')
PREBUILT_CLANG_TOOLS_CLANG = os.path.join(PREBUILT_CLANG_TOOLS, 'clang')
PREBUILT_CLANG_BIN = os.path.join(
    PREBUILT_CLANG, 'third_party', 'llvm-build', 'Release+Asserts', 'bin')
CC = os.path.join(PREBUILT_CLANG_BIN, 'clang')
CXX = os.path.join(PREBUILT_CLANG_BIN, 'clang++')

LLVM_OUT_DIR = os.path.join(WORK_DIR, 'llvm-out')
V8_OUT_DIR = os.path.join(V8_SRC_DIR, 'out', 'Release')
SEXPR_OUT_DIR = os.path.join(SEXPR_SRC_DIR, 'out')
BINARYEN_OUT_DIR = os.path.join(WORK_DIR, 'binaryen-out')
BINARYEN_BIN_DIR = os.path.join(BINARYEN_OUT_DIR, 'bin')
TORTURE_S_OUT_DIR = os.path.join(WORK_DIR, 'torture-s')

INSTALL_DIR = os.path.join(WORK_DIR, 'wasm-install')
INSTALL_BIN = os.path.join(INSTALL_DIR, 'bin')
INSTALL_LIB = os.path.join(INSTALL_DIR, 'lib')

# Avoid flakes: use cached repositories to avoid relying on external network.
GITHUB_REMOTE = 'github'
GITHUB_SSH = 'git@github.com:'
GIT_MIRROR_BASE = 'https://chromium.googlesource.com/'
WASM_GIT_BASE = GIT_MIRROR_BASE + 'external/github.com/WebAssembly/'
LLVM_GIT = GIT_MIRROR_BASE + 'chromiumos/third_party/llvm'
CLANG_GIT = GIT_MIRROR_BASE + 'chromiumos/third_party/clang'
PREBUILT_CLANG_GIT = GIT_MIRROR_BASE + 'chromium/src/tools/clang'
V8_GIT = GIT_MIRROR_BASE + 'v8/v8'
GCC_GIT = GIT_MIRROR_BASE + 'chromiumos/third_party/gcc'
SEXPR_GIT = WASM_GIT_BASE + 'sexpr-wasm-prototype.git'
SPEC_GIT = WASM_GIT_BASE + 'spec.git'
BINARYEN_GIT = WASM_GIT_BASE + 'binaryen.git'

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

NPROC = multiprocessing.cpu_count()

# Schedulers which can kick off new builds, from:
# https://chromium.googlesource.com/chromium/tools/build/+/master/masters/master.client.wasm.llvm/builders.pyl
SCHEDULERS = {
    None: 'forced',
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


# Magic annotations:
# https://chromium.googlesource.com/chromium/tools/build/+/master/scripts/common/annotator.py
def BuildStep(name):
  sys.stdout.write('\n@@@BUILD_STEP %s@@@\n' % name)


def StepLink(label, url):
  sys.stdout.write('@@@STEP_LINK@%s@%s@@@\n' % (label, url))


failed_steps = 0


def StepFail():
  """Mark one step as failing, but keep going."""
  sys.stdout.write('\n@@@STEP_FAILURE@@@\n')
  global failed_steps
  failed_steps += 1


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


def UploadToCloud(local, remote, link_name):
  """Upload file to Cloud Storage."""
  if not os.environ.get('BUILDBOT_BUILDERNAME'):
    return
  remote = CLOUD_STORAGE_PATH + remote
  proc.check_call(
      ['gsutil', 'cp', '-a', 'public-read', local, 'gs://' + remote])
  StepLink(link_name, CLOUD_STORAGE_BASE_URL + remote)


def CopyCloudStorage(copy_from, copy_to, link_name):
  """Copy from one Cloud Storage file to another."""
  if not os.environ.get('BUILDBOT_BUILDERNAME'):
    return
  copy_from = CLOUD_STORAGE_PATH + copy_from
  copy_to = CLOUD_STORAGE_PATH + copy_to
  proc.check_call(
      ['gsutil', 'cp', '-a', 'public-read',
       'gs://' + copy_from, 'gs://' + copy_to])
  StepLink(link_name, CLOUD_STORAGE_BASE_URL + copy_to)


def Archive(name, tar):
  """Archive the tar file with the given name, and with the LLVM git hash."""
  if not os.environ.get('BUILDBOT_BUILDERNAME'):
    return
  git_gs = 'git/wasm-%s-%s.tbz2' % (name, BUILDBOT_BUILDNUMBER)
  UploadToCloud(tar, git_gs, 'download')


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


def CurrentGitInfo(cwd):
  def pretty(fmt):
    return proc.check_output(
        ['git', 'log', '-n1', '--pretty=format:%s' % fmt], cwd=cwd).strip()
  remote = proc.check_output(['git', 'config', '--get', 'remote.origin.url'],
                             cwd=cwd).strip()
  return {
      'hash': pretty('%H'),
      'name': pretty('%aN'),
      'email': pretty('%ae'),
      'subject': pretty('%s'),
      'remote': remote,
  }


def GitCloneFetchCheckout(name, work_dir, git_repo, rebase_master=False,
                          checkout='origin/master', depth=None):
  """Clone a git repo if not already cloned, then fetch and checkout."""
  if os.path.isdir(work_dir):
    print '%s directory already exists' % name
  else:
    clone = ['git', 'clone', git_repo, work_dir]
    if depth:
      clone.append('--depth')
      clone.append(str(depth))
    proc.check_call(clone)
    if rebase_master:
      GitConfigRebaseMaster(work_dir)
  proc.check_call(['git', 'fetch'], cwd=work_dir)
  proc.check_call(['git', 'checkout', checkout], cwd=work_dir)
  AddGithubRemote(work_dir)
  return (name, work_dir)


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


def GitConfigRebaseMaster(cwd):
  """Avoid generating a non-linear history in the clone

  The upstream repository is in Subversion. Use `git pull --rebase` instead of
  git pull: llvm.org/docs/GettingStarted.html#git-mirror
  """
  proc.check_call(
      ['git', 'config', 'branch.master.rebase', 'true'], cwd=cwd)


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


def SyncPrebuiltClang():
  if os.path.isdir(PREBUILT_CLANG_TOOLS_CLANG):
    print 'Prebuilt Chromium Clang directory already exists'
  else:
    print 'Cloning Prebuilt Chromium Clang directory'
    Mkdir(PREBUILT_CLANG)
    Mkdir(PREBUILT_CLANG_TOOLS)
    proc.check_call(
        ['git', 'clone', PREBUILT_CLANG_GIT, PREBUILT_CLANG_TOOLS_CLANG])
  proc.check_call(['git', 'fetch'], cwd=PREBUILT_CLANG_TOOLS_CLANG)
  proc.check_call(
      [os.path.join(PREBUILT_CLANG_TOOLS_CLANG, 'scripts', 'update.py')])
  assert os.path.isfile(CC), 'Expect clang at %s' % CC
  assert os.path.isfile(CXX), 'Expect clang++ at %s' % CXX
  return ('chromium-clang', PREBUILT_CLANG_TOOLS_CLANG)


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
    BuildStep('Clobbering work dir')
    if os.path.isdir(WORK_DIR):
      shutil.rmtree(WORK_DIR)


def SyncRepos():
  BuildStep('Sync Repos')
  repos = [
      ('waterfall', SCRIPT_DIR),
      GitCloneFetchCheckout(name='llvm', work_dir=LLVM_SRC_DIR,
                            git_repo=LLVM_GIT),
      GitCloneFetchCheckout(name='clang', work_dir=CLANG_SRC_DIR,
                            git_repo=CLANG_GIT),
      GitCloneFetchCheckout(name='gcc', work_dir=GCC_SRC_DIR, git_repo=GCC_GIT,
                            checkout=GCC_REVISION, depth=GCC_CLONE_DEPTH),
      ChromiumFetchSync(name='v8', git_repo=V8_GIT, work_dir=V8_SRC_DIR),
      SyncPrebuiltClang(),
      GitCloneFetchCheckout(name='sexpr', work_dir=SEXPR_SRC_DIR,
                            git_repo=SEXPR_GIT),
      GitCloneFetchCheckout(name='spec', work_dir=SPEC_SRC_DIR,
                            git_repo=SPEC_GIT),
      GitCloneFetchCheckout(name='binaryen', work_dir=BINARYEN_SRC_DIR,
                            git_repo=BINARYEN_GIT)
  ]
  SyncLLVMClang()
  SyncOCaml()
  # Keep track of all repo information here, preventing the summary from
  # getting out of sync with the actual list of repos.
  info = {}
  for r in repos:
    info[r[0]] = CurrentGitInfo(r[1])
  return info


def LLVM():
  BuildStep('LLVM')
  Mkdir(LLVM_OUT_DIR)
  proc.check_call(
      ['cmake', '-G', 'Ninja', LLVM_SRC_DIR,
       '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
       '-DLLVM_BUILD_TESTS=ON',
       '-DCMAKE_C_COMPILER=' + CC,
       '-DCMAKE_CXX_COMPILER=' + CXX,
       '-DCMAKE_BUILD_TYPE=Release',
       '-DCMAKE_INSTALL_PREFIX=' + INSTALL_DIR,
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
  BuildStep('V8')
  proc.check_call(['ninja', '-C', V8_OUT_DIR, 'd8', 'unittests'],
                  cwd=V8_SRC_DIR)
  proc.check_call(['tools/run-tests.py', 'unittests',
                   '--shell-dir', V8_OUT_DIR],
                  cwd=V8_SRC_DIR)
  to_archive = ['d8', 'natives_blob.bin', 'snapshot_blob.bin']
  for a in to_archive:
    CopyBinaryToArchive(os.path.join(V8_OUT_DIR, a))


def Sexpr():
  BuildStep('Sexpr')
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
  BuildStep('OCaml')
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
  BuildStep('spec')
  # Spec builds in-tree. Always clobber and run the tests.
  proc.check_call(['make', 'clean'], cwd=ML_DIR)
  proc.check_call(['make', 'all'], cwd=ML_DIR)
  wasm = os.path.join(ML_DIR, 'wasm.opt')
  CopyBinaryToArchive(wasm)


def Binaryen():
  BuildStep('binaryen')
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


def ArchiveBinaries():
  BuildStep('Archive binaries')
  # All relevant binaries were copied to the LLVM directory.
  Archive('binaries', Tar(INSTALL_DIR, print_content=True))


def CompileLLVMTorture():
  name = 'Compile LLVM Torture'
  BuildStep(name)
  c = os.path.join(LLVM_OUT_DIR, 'bin', 'clang')
  cxx = os.path.join(LLVM_OUT_DIR, 'bin', 'clang++')
  Remove(TORTURE_S_OUT_DIR)
  Mkdir(TORTURE_S_OUT_DIR)
  unexpected_result_count = compile_torture_tests.run(
      c=c, cxx=cxx, testsuite=GCC_TEST_DIR,
      fails=LLVM_KNOWN_TORTURE_FAILURES,
      out=TORTURE_S_OUT_DIR)
  Archive('torture-s', Tar(TORTURE_S_OUT_DIR))
  if 0 != unexpected_result_count:
    StepFail()


def LinkLLVMTorture(name, linker, fails):
  BuildStep('Link LLVM Torture with %s' % name)
  assert os.path.isfile(linker), 'Cannot find linker at %s' % linker
  assembly_files = os.path.join(TORTURE_S_OUT_DIR, '*.s')
  out = os.path.join(WORK_DIR, 'torture-%s' % name)
  Remove(out)
  Mkdir(out)
  unexpected_result_count = link_assembly_files.run(
      linker=linker, files=assembly_files, fails=fails, out=out)
  Archive('torture-%s' % name, Tar(out))
  if 0 != unexpected_result_count:
    StepFail()
  return out


def AssembleLLVMTorture(name, assembler, indir, fails):
  BuildStep('Assemble LLVM Torture with %s' % name)
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
    StepFail()
  return out


def ExecuteLLVMTorture(name, runner, indir, fails, extension, has_output,
                       wasmjs, is_flaky=False):
  BuildStep('Execute LLVM Torture with %s' % name)
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
      wasmjs=wasmjs)
  if has_output:
    Archive('torture-%s' % name, Tar(out))
  if 0 != unexpected_result_count:
    if not is_flaky:
      StepFail()
  return out


def Summary(repos):
  BuildStep('Summary')
  info = {'repositories': repos}
  info['build'] = BUILDBOT_BUILDNUMBER
  info['scheduler'] = SCHEDULER
  info_json = json.dumps(info)
  print info
  print 'Failed steps: %s.' % failed_steps
  with open('latest', 'w+') as f:
    f.write(info_json)
  UploadToCloud('latest', 'git/latest', 'latest')
  if failed_steps:
    StepFail()
  else:
    with open('lkgr', 'w+') as f:
      f.write(info_json)
    UploadToCloud('lkgr', 'git/lkgr', 'lkgr')


def main():
  Clobber()
  Chdir(SCRIPT_DIR)
  Mkdir(WORK_DIR)
  Remove(INSTALL_DIR)
  repos = SyncRepos()
  LLVM()
  V8()
  Sexpr()
  OCaml()
  Spec()
  Binaryen()
  ArchiveBinaries()
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
      wasmjs=None,
      is_flaky=True)  # TODO binaryen-shell is flaky when running tests.
  ExecuteLLVMTorture(
      name='d8',
      runner=os.path.join(INSTALL_BIN, 'd8'),
      indir=sexpr_wasm_out,
      fails=V8_KNOWN_TORTURE_FAILURES,
      extension='wasm',
      has_output=False,
      wasmjs=WASMJS)
  # Keep the summary step last: it'll be marked as red if the return code is
  # non-zero. Individual steps are marked as red with StepFail().
  Summary(repos)
  return failed_steps


if __name__ == '__main__':
  sys.exit(main())
