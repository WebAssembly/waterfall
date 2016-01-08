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

import os
import shutil
import sys
import multiprocessing
import urllib2

import assemble_files
import compile_torture_tests
import link_assembly_files
import proc


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.path.join(SCRIPT_DIR, 'work')

CLOUD_STORAGE_BASE_URL = 'https://storage.googleapis.com/'
CLOUD_STORAGE_PATH = 'wasm-llvm/builds/'

IT_IS_KNOWN = 'known_gcc_test_failures.txt'

LLVM_SRC_DIR = os.path.join(WORK_DIR, 'llvm')
CLANG_SRC_DIR = os.path.join(LLVM_SRC_DIR, 'tools', 'clang')
LLVM_KNOWN_TORTURE_FAILURES = os.path.join(LLVM_SRC_DIR, 'lib', 'Target',
                                           'WebAssembly', IT_IS_KNOWN)

GCC_SRC_DIR = os.path.join(WORK_DIR, 'gcc')
GCC_TEST_DIR = os.path.join(GCC_SRC_DIR, 'gcc', 'testsuite')

SEXPR_SRC_DIR = os.path.join(WORK_DIR, 'sexpr-wasm-prototype')
SEXPR_S2WASM_KNOWN_TORTURE_FAILURES = os.path.join(SEXPR_SRC_DIR, 's2wasm_' +
                                                   IT_IS_KNOWN)

SPEC_SRC_DIR = os.path.join(WORK_DIR, 'spec')
ML_DIR = os.path.join(SPEC_SRC_DIR, 'ml-proto')
BINARYEN_SRC_DIR = os.path.join(WORK_DIR, 'binaryen')
S2WASM_KNOWN_TORTURE_FAILURES = os.path.join(BINARYEN_SRC_DIR, 'test',
                                             's2wasm_' + IT_IS_KNOWN)

PREBUILT_CLANG = os.path.join(WORK_DIR, 'chromium-clang')
PREBUILT_CLANG_TOOLS = os.path.join(PREBUILT_CLANG, 'tools')
PREBUILT_CLANG_TOOLS_CLANG = os.path.join(PREBUILT_CLANG_TOOLS, 'clang')
PREBUILT_CLANG_BIN = os.path.join(
    PREBUILT_CLANG, 'third_party', 'llvm-build', 'Release+Asserts', 'bin')
CC = os.path.join(PREBUILT_CLANG_BIN, 'clang')
CXX = os.path.join(PREBUILT_CLANG_BIN, 'clang++')

LLVM_OUT_DIR = os.path.join(WORK_DIR, 'llvm-out')
LLVM_INSTALL_DIR = os.path.join(WORK_DIR, 'llvm-install')
LLVM_INSTALL_BIN = os.path.join(LLVM_INSTALL_DIR, 'bin')
SEXPR_OUT_DIR = os.path.join(SEXPR_SRC_DIR, 'out')
BINARYEN_OUT_DIR = os.path.join(WORK_DIR, 'binaryen-out')
BINARYEN_BIN_DIR = os.path.join(BINARYEN_OUT_DIR, 'bin')
TORTURE_S_OUT_DIR = os.path.join(WORK_DIR, 'torture-s')

# Avoid flakes: use cached repositories to avoid relying on external network.
GITHUB_REMOTE = 'github'
GITHUB_SSH = 'git@github.com:'
GIT_MIRROR_BASE = 'https://chromium.googlesource.com/'
WASM_GIT_BASE = GIT_MIRROR_BASE + 'external/github.com/WebAssembly/'
LLVM_GIT = GIT_MIRROR_BASE + 'chromiumos/third_party/llvm'
CLANG_GIT = GIT_MIRROR_BASE + 'chromiumos/third_party/clang'
PREBUILT_CLANG_GIT = GIT_MIRROR_BASE + 'chromium/src/tools/clang'
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

# Try to use the LLVM revision provided by buildbot.
LLVM_REVISION = os.environ.get('BUILDBOT_REVISION', 'None')
if LLVM_REVISION == 'None':
  LLVM_REVISION = 'origin/master'

# Pin the GCC revision so that new torture tests don't break the bot. This
# should be manually updated when convenient.
GCC_REVISION = 'b6125c702850488ac3bfb1079ae5c9db89989406'


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
  print 'Copying binary %s to archive %s' % (binary, LLVM_INSTALL_BIN)
  shutil.copy2(binary, LLVM_INSTALL_BIN)


def Tar(directory):
  """Create a tar file from directory."""
  assert os.path.isdir(directory), 'Must tar a directory to avoid tarbombs'
  (up_directory, basename) = os.path.split(directory)
  tar = os.path.join(up_directory, basename + '.tbz2')
  Remove(tar)
  print 'Creating %s from %s/%s' % (tar, up_directory, basename)
  proc.check_call(['tar', 'cjf', tar, basename], cwd=up_directory)
  return tar


def UploadToCloud(local, remote, link_name):
  """Upload file to Cloud Storage."""
  if not os.environ.get('BUILDBOT_BUILDERNAME'):
    return
  remote = CLOUD_STORAGE_PATH + remote
  print 'Uploading %s to %s' % (local, remote)
  proc.check_call(
      ['gsutil', 'cp', '-a', 'public-read', local, 'gs://' + remote])
  StepLink(link_name, CLOUD_STORAGE_BASE_URL + remote)


def CopyCloudStorage(copy_from, copy_to, link_name):
  """Copy from one Cloud Storage file to another."""
  if not os.environ.get('BUILDBOT_BUILDERNAME'):
    return
  copy_from = CLOUD_STORAGE_PATH + copy_from
  copy_to = CLOUD_STORAGE_PATH + copy_to
  print 'Copying %s to %s' % (copy_from, copy_to)
  proc.check_call(
      ['gsutil', 'cp', '-a', 'public-read',
       'gs://' + copy_from, 'gs://' + copy_to])
  StepLink(link_name, CLOUD_STORAGE_BASE_URL + copy_to)


def Archive(name, tar):
  """Archive the tar file with the given name, and with the LLVM git hash."""
  if not os.environ.get('BUILDBOT_BUILDERNAME'):
    return
  print 'Archiving %s: %s' % (name, tar)
  git_gs = 'git/wasm-%s-%s.tbz2' % (name, LLVM_REVISION)
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


def GitCloneFetchCheckout(name, work_dir, git_repo, checkout='origin/master'):
  """Clone a git repo if not already cloned, then fetch and checkout."""
  if os.path.isdir(work_dir):
    print '%s directory already exists' % name
  else:
    print 'Cloning %s from %s into %s' % (name, git_repo, work_dir)
    proc.check_call(['git', 'clone', git_repo, work_dir])
  print 'Syncing %s' % name
  proc.check_call(['git', 'fetch'], cwd=work_dir)
  print 'Checking out %s' % checkout
  proc.check_call(['git', 'checkout', checkout], cwd=work_dir)
  PrintCurrentGitRev(work_dir)
  AddGithubRemote(work_dir)


def GitConfigRebaseMaster(cwd):
  """Avoid generating a non-linear history in the clone

  The upstream repository is in Subversion. Use `git pull --rebase` instead of
  git pull: llvm.org/docs/GettingStarted.html#git-mirror
  """
  proc.check_call(
      ['git', 'config', 'branch.master.rebase', 'true'], cwd=cwd)


def PrintCurrentGitRev(cwd):
  log = proc.check_output(
      ['git', 'log', '--oneline', '-n1'], cwd=cwd).strip()
  remote = proc.check_output(
      ['git', 'config', '--get', 'remote.origin.url'], cwd=cwd).strip()
  sys.stdout.write('%s from remote %s is at revision %s\n' %
                   (cwd, remote, log))


def FindPriorRev(path, goal):
  revs = proc.check_output(
      ['git', 'rev-list', 'origin/master'], cwd=path).splitlines()
  for rev in revs:
    num = proc.check_output(
        ['git', 'svn', 'find-rev', rev], cwd=path).strip()
    if int(num) <= goal:
      return rev
  raise Exception('Cannot find clang rev at or before %d' % goal)


def SyncLLVMClang():
  if os.path.isdir(LLVM_SRC_DIR):
    assert os.path.isdir(CLANG_SRC_DIR), 'Assuming LLVM implies Clang'
    print 'LLVM and Clang directories already exist'
  else:
    print 'Cloning LLVM and Clang'
    proc.check_call(['git', 'clone', LLVM_GIT, LLVM_SRC_DIR])
    GitConfigRebaseMaster(LLVM_SRC_DIR)
    proc.check_call(['git', 'clone', CLANG_GIT, CLANG_SRC_DIR])
    GitConfigRebaseMaster(CLANG_SRC_DIR)
  print 'Syncing LLVM'
  proc.check_call(['git', 'fetch'], cwd=LLVM_SRC_DIR)
  proc.check_call(['git', 'checkout', LLVM_REVISION], cwd=LLVM_SRC_DIR)
  print 'Getting SVN rev'
  llvm_svn_rev = int(proc.check_output(
      ['git', 'svn', 'find-rev', 'HEAD'], cwd=LLVM_SRC_DIR).strip())
  print 'SVN REV: %d' % llvm_svn_rev
  print 'Finding prior Clang rev'
  proc.check_call(['git', 'fetch'], cwd=CLANG_SRC_DIR)
  prior_rev = FindPriorRev(CLANG_SRC_DIR, llvm_svn_rev)
  print 'Checking out Clang rev: %s' % prior_rev
  proc.check_call(['git', 'checkout', prior_rev], cwd=CLANG_SRC_DIR)
  PrintCurrentGitRev(LLVM_SRC_DIR)
  PrintCurrentGitRev(CLANG_SRC_DIR)


def SyncPrebuiltClang():
  if os.path.isdir(PREBUILT_CLANG_TOOLS_CLANG):
    print 'Prebuilt Chromium Clang directory already exists'
  else:
    print 'Cloning Prebuilt Chromium Clang directory'
    Mkdir(PREBUILT_CLANG)
    Mkdir(PREBUILT_CLANG_TOOLS)
    proc.check_call(
        ['git', 'clone', PREBUILT_CLANG_GIT, PREBUILT_CLANG_TOOLS_CLANG])
  print 'Syncing Prebuilt Chromium Clang scripts'
  proc.check_call(['git', 'fetch'], cwd=PREBUILT_CLANG_TOOLS_CLANG)
  print 'Syncing Prebuilt Chromium Clang'
  proc.check_call(
      [os.path.join(PREBUILT_CLANG_TOOLS_CLANG, 'scripts', 'update.py')])
  assert os.path.isfile(CC), 'Expect clang at %s' % CC
  assert os.path.isfile(CXX), 'Expect clang++ at %s' % CXX
  PrintCurrentGitRev(PREBUILT_CLANG_TOOLS_CLANG)


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
    print 'Download done, untar %s' % OCAML_TAR
    proc.check_call(['tar', '-xvf', OCAML_TAR], cwd=WORK_DIR)
    assert os.path.isdir(OCAML_DIR), 'Untar should produce %s' % OCAML_DIR


def Clobber():
  if os.environ.get('BUILDBOT_CLOBBER'):
    BuildStep('Clobbering work dir')
    if os.path.isdir(WORK_DIR):
      print 'Removing %s' % WORK_DIR
      shutil.rmtree(WORK_DIR)


def SyncRepos():
  BuildStep('Sync Repos')
  PrintCurrentGitRev(SCRIPT_DIR)
  SyncLLVMClang()
  GitCloneFetchCheckout(name='GCC', work_dir=GCC_SRC_DIR, git_repo=GCC_GIT,
                        checkout=GCC_REVISION)
  SyncPrebuiltClang()
  GitCloneFetchCheckout(name='sexpr', work_dir=SEXPR_SRC_DIR,
                        git_repo=SEXPR_GIT)
  SyncOCaml()
  GitCloneFetchCheckout(name='spec', work_dir=SPEC_SRC_DIR, git_repo=SPEC_GIT)
  GitCloneFetchCheckout(name='binaryen', work_dir=BINARYEN_SRC_DIR,
                        git_repo=BINARYEN_GIT)


def BuildLLVM():
  BuildStep('Build LLVM')
  print 'Running cmake on llvm'
  Mkdir(LLVM_OUT_DIR)
  proc.check_call(
      ['cmake', '-G', 'Ninja', LLVM_SRC_DIR,
       '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
       '-DLLVM_BUILD_TESTS=ON',
       '-DCMAKE_C_COMPILER=' + CC,
       '-DCMAKE_CXX_COMPILER=' + CXX,
       '-DCMAKE_BUILD_TYPE=Release',
       '-DCMAKE_INSTALL_PREFIX=' + LLVM_INSTALL_DIR,
       '-DLLVM_ENABLE_ASSERTIONS=ON',
       '-DLLVM_EXPERIMENTAL_TARGETS_TO_BUILD=WebAssembly',
       '-DLLVM_TARGETS_TO_BUILD=X86'], cwd=LLVM_OUT_DIR)
  print 'Running ninja'
  proc.check_call(['ninja'], cwd=LLVM_OUT_DIR)


def TestLLVM():
  BuildStep('Test LLVM')
  proc.check_call(['ninja', 'check-all'], cwd=LLVM_OUT_DIR)


def InstallLLVM():
  BuildStep('Install LLVM')
  Remove(LLVM_INSTALL_DIR)
  proc.check_call(['ninja', 'install'], cwd=LLVM_OUT_DIR)


def BuildSexpr():
  BuildStep('Build Sexpr')
  # sexpr-wasm builds in its own in-tree out/ folder. The build is fast, so
  # always clobber.
  proc.check_call(['make', 'clean'], cwd=SEXPR_SRC_DIR)
  proc.check_call(['make',
                   'CC=%s' % CC,
                   'CXX=%s' % CXX],
                  cwd=SEXPR_SRC_DIR)
  sexpr = os.path.join(SEXPR_OUT_DIR, 'sexpr-wasm')
  CopyBinaryToArchive(sexpr)


def BuildOCaml():
  BuildStep('Build OCaml')
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


def BuildSpec():
  BuildStep('Build spec')
  # Spec builds in-tree. Always clobber and run the tests.
  proc.check_call(['make', 'clean'], cwd=ML_DIR)
  proc.check_call(['make', 'all'], cwd=ML_DIR)
  wasm = os.path.join(ML_DIR, 'wasm.opt')
  CopyBinaryToArchive(wasm)


def BuildBinaryen():
  BuildStep('Build binaryen')
  Mkdir(BINARYEN_OUT_DIR)
  proc.check_call(
      ['cmake', '-G', 'Ninja', BINARYEN_SRC_DIR,
       '-DCMAKE_C_COMPILER=' + CC,
       '-DCMAKE_CXX_COMPILER=' + CXX],
      cwd=BINARYEN_OUT_DIR)
  print 'Running ninja'
  proc.check_call(['ninja'], cwd=BINARYEN_OUT_DIR)
  assert os.path.isdir(BINARYEN_BIN_DIR), 'Expected %s' % BINARYEN_BIN_DIR
  for node in os.listdir(BINARYEN_BIN_DIR):
    f = os.path.join(BINARYEN_BIN_DIR, node)
    if os.path.isfile(f):
      CopyBinaryToArchive(f)


def ArchiveBinaries():
  if LLVM_REVISION == 'origin/master':
    return
  BuildStep('Archive binaries')
  # All relevant binaries were copied to the LLVM directory.
  Archive('binaries', Tar(LLVM_INSTALL_DIR))


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


def Summary():
  BuildStep('Summary')
  sys.stdout.write('Failed steps: %s.' % failed_steps)
  with open('latest', 'w+') as f:
    f.write(str(LLVM_REVISION))
  UploadToCloud('latest', 'git/latest', 'latest')
  if failed_steps:
    StepFail()
  else:
    try:
      with open('lkgr', 'w+') as f:
        f.write(str(LLVM_REVISION))
      UploadToCloud('lkgr', 'git/lkgr', 'lkgr')
    finally:
      Remove('lkgr')


def main():
  Clobber()
  Chdir(SCRIPT_DIR)
  Mkdir(WORK_DIR)
  SyncRepos()
  BuildLLVM()
  TestLLVM()
  InstallLLVM()
  BuildSexpr()
  BuildOCaml()
  BuildSpec()
  BuildBinaryen()
  ArchiveBinaries()
  CompileLLVMTorture()
  s2wasm_out = LinkLLVMTorture(
      name='s2wasm',
      linker=os.path.join(LLVM_INSTALL_BIN, 's2wasm'),
      fails=S2WASM_KNOWN_TORTURE_FAILURES)
  s2wasm_sexpr_wasm_out = AssembleLLVMTorture(
      name='s2wasm-sexpr-wasm',
      assembler=os.path.join(LLVM_INSTALL_BIN, 'sexpr-wasm'),
      indir=s2wasm_out,
      fails=SEXPR_S2WASM_KNOWN_TORTURE_FAILURES)
  # Keep the summary step last: it'll be marked as red if the return code is
  # non-zero. Individual steps are marked as red with StepFail().
  Summary()
  return failed_steps


if __name__ == '__main__':
  sys.exit(main())
