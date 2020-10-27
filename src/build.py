#!/usr/bin/env python3
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
import zipfile

import buildbot
import cloud
import compile_torture_tests
import execute_files
from file_util import Chdir, CopyTree, Mkdir, Remove
import host_toolchains
import link_assembly_files
import proc
import testing
import work_dirs
from urllib.request import urlopen, URLError

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSVU_OUT_DIR = os.path.expanduser(os.path.join('~', '.jsvu'))

# This file has a special path to avoid warnings about the system being unknown
CMAKE_TOOLCHAIN_FILE = 'Wasi.cmake'

EMSCRIPTEN_CONFIG_UPSTREAM = 'emscripten_config_upstream'

# Avoid flakes: use cached repositories to avoid relying on external network.
GIT_MIRROR_BASE = 'https://chromium.googlesource.com/'
GITHUB_MIRROR_BASE = GIT_MIRROR_BASE + 'external/github.com/'
WASM_GIT_BASE = GITHUB_MIRROR_BASE + 'WebAssembly/'
EMSCRIPTEN_GIT_BASE = 'https://github.com/emscripten-core/'
LLVM_GIT_BASE = 'https://github.com/llvm/'

# Name of remote for build script to use. Don't touch origin to avoid
# clobbering any local development.
WATERFALL_REMOTE = '_waterfall'

WASM_STORAGE_BASE = 'https://wasm.storage.googleapis.com/'

GNUWIN32_ZIP = 'gnuwin32.zip'

# This version is the current LLVM version in development. This needs to be
# manually updated to the latest x.0.0 version whenever LLVM starts development
# on a new major version. This is so our manual build of compiler-rt is put
# where LLVM expects it.
LLVM_VERSION = '12.0.0'

# Update this number each time you want to create a clobber build.  If the
# clobber_version.txt file in the build dir doesn't match we remove ALL work
# dirs.  This works like a simpler version of chromium's landmine feature.
CLOBBER_BUILD_TAG = 19

V8_BUILD_SUBDIR = os.path.join('out.gn', 'x64.release')

LINUX_SYSROOT = 'sysroot_ubuntu_bionic_amd64'
LINUX_SYSROOT_URL = WASM_STORAGE_BASE + LINUX_SYSROOT + '_v1.tar.xz'

options = None


def GccTestDir():
    return GetSrcDir('gcc', 'gcc', 'testsuite')


def GetBuildDir(*args):
    return os.path.join(work_dirs.GetBuild(), *args)


def GetPrebuilt(*args):
    return os.path.join(work_dirs.GetPrebuilt(), *args)


def GetPrebuiltClang(binary):
    return os.path.join(work_dirs.GetV8(), 'third_party', 'llvm-build',
                        'Release+Asserts', 'bin', binary)


def GetSrcDir(*args):
    return os.path.join(work_dirs.GetSync(), *args)


def GetInstallDir(*args):
    return os.path.join(work_dirs.GetInstall(), *args)


def GetTestDir(*args):
    return os.path.join(work_dirs.GetTest(), *args)


def GetLLVMSrcDir(*args):
    return GetSrcDir('llvm-project', *args)


def IsWindows():
    return sys.platform == 'win32'


def IsLinux():
    return sys.platform.startswith('linux')


def IsMac():
    return sys.platform == 'darwin'


def Executable(name, extension='.exe'):
    return name + extension if IsWindows() else name


def WindowsFSEscape(path):
    return os.path.normpath(path).replace('\\', '/')


# Use prebuilt Node.js because the buildbots don't have node preinstalled
NODE_VERSION = '12.18.1'
NODE_BASE_NAME = 'node-v' + NODE_VERSION + '-'


def NodePlatformName():
    return {
        'darwin': 'darwin-x64',
        'linux': 'linux-x64',
        'linux2': 'linux-x64',
        'win32': 'win-x64'
    }[sys.platform]


def NodeBinDir():
    node_subdir = NODE_BASE_NAME + NodePlatformName()
    if IsWindows():
        return GetPrebuilt(node_subdir)
    return GetPrebuilt(node_subdir, 'bin')


def NodeBin():
    return Executable(os.path.join(NodeBinDir(), 'node'))


def CMakePlatformName():
    return {
        'linux': 'Linux',
        'linux2': 'Linux',
        'darwin': 'Darwin',
        'win32': 'win64'
    }[sys.platform]


def CMakeArch():
    return 'x64' if IsWindows() else 'x86_64'


PREBUILT_CMAKE_VERSION = '3.15.3'
PREBUILT_CMAKE_BASE_NAME = 'cmake-%s-%s-%s' % (
    PREBUILT_CMAKE_VERSION, CMakePlatformName(), CMakeArch())


def PrebuiltCMakeDir(*args):
    return GetPrebuilt(PREBUILT_CMAKE_BASE_NAME, *args)


def PrebuiltCMakeBin():
    if IsMac():
        bin_dir = os.path.join('CMake.app', 'Contents', 'bin')
    else:
        bin_dir = 'bin'
    return PrebuiltCMakeDir(bin_dir, 'cmake')


def BuilderPlatformName():
    return {
        'linux': 'linux',
        'linux2': 'linux',
        'darwin': 'mac',
        'win32': 'windows'
    }[sys.platform]


def D8Bin():
    if IsMac():
        return os.path.join(JSVU_OUT_DIR, 'v8')
    return Executable(GetInstallDir('bin', 'd8'))


# Java installed in the buildbots are too old while emscripten uses closure
# compiler that requires Java SE 8.0 (version 52) or above
JAVA_VERSION = '9.0.1'


def JavaDir():
    outdir = GetPrebuilt('jre-' + JAVA_VERSION)
    if IsMac():
        outdir += '.jre'
    return outdir


def JavaBin():
    if IsMac():
        bin_dir = os.path.join('Contents', 'Home', 'bin')
    else:
        bin_dir = 'bin'
    return Executable(os.path.join(JavaDir(), bin_dir, 'java'))


# Known failures.
IT_IS_KNOWN = 'known_gcc_test_failures.txt'
ASM2WASM_KNOWN_TORTURE_COMPILE_FAILURES = [
    os.path.join(SCRIPT_DIR, 'test', 'asm2wasm_compile_' + IT_IS_KNOWN)
]
EMWASM_KNOWN_TORTURE_COMPILE_FAILURES = [
    os.path.join(SCRIPT_DIR, 'test', 'emwasm_compile_' + IT_IS_KNOWN)
]

RUN_KNOWN_TORTURE_FAILURES = [
    os.path.join(SCRIPT_DIR, 'test', 'run_' + IT_IS_KNOWN)
]
LLD_KNOWN_TORTURE_FAILURES = [
    os.path.join(SCRIPT_DIR, 'test', 'lld_' + IT_IS_KNOWN)
]

# Exclusions (known failures are compiled and run, and expected to fail,
# whereas exclusions are not even run, e.g. because they have UB which
# results in infinite loops)
LLVM_TORTURE_EXCLUSIONS = [
    os.path.join(SCRIPT_DIR, 'test', 'llvm_torture_exclusions')
]

RUN_LLVM_TESTSUITE_FAILURES = [
    os.path.join(SCRIPT_DIR, 'test', 'llvmtest_known_failures.txt')
]

# Optimization levels
BARE_TEST_OPT_FLAGS = ['O0', 'O2']
EMSCRIPTEN_TEST_OPT_FLAGS = ['O0', 'O3']

NPROC = multiprocessing.cpu_count()

if IsMac():
    # Experimental temp fix for crbug.com/829034 stdout write sometimes fails
    from fcntl import fcntl, F_GETFL, F_SETFL
    fd = sys.stdout.fileno()
    flags = fcntl(fd, F_GETFL)
    fcntl(fd, F_SETFL, flags & ~os.O_NONBLOCK)

# Pin the GCC revision so that new torture tests don't break the bot. This
# should be manually updated when convenient.
GCC_REVISION = 'b6125c702850488ac3bfb1079ae5c9db89989406'
GCC_CLONE_DEPTH = 1000


def CopyBinaryToArchive(binary, prefix=''):
    """All binaries are archived in the same tar file."""
    install_bin = GetInstallDir(prefix, 'bin')
    print('Copying binary %s to archive %s' % (binary, install_bin))
    Mkdir(install_bin)
    shutil.copy2(binary, install_bin)


def CopyLibraryToArchive(library, prefix=''):
    """All libraries are archived in the same tar file."""
    install_lib = GetInstallDir(prefix, 'lib')
    print('Copying library %s to archive %s' % (library, install_lib))
    Mkdir(install_lib)
    shutil.copy2(library, install_lib)


def CopyLibraryToSysroot(library):
    """All libraries are archived in the same tar file."""
    install_lib = GetInstallDir('sysroot', 'lib', 'wasm32-wasi')
    print('Copying library %s to archive %s' % (library, install_lib))
    Mkdir(install_lib)
    shutil.copy2(library, install_lib)


def Archive(directory, print_content=False):
    """Create an archive file from directory."""
    # Use the format "native" to the platform
    if IsWindows():
        archive = Zip(directory, print_content)
    else:
        archive = Tar(directory, print_content)
    print('Archive created: %s [%s]' % (archive, os.path.getsize(archive)))
    return archive


def Tar(directory, print_content=False):
    assert os.path.isdir(directory), 'Must tar a directory to avoid tarbombs'
    up_directory, basename = os.path.split(directory)
    tar = os.path.join(up_directory, basename + '.tbz2')
    Remove(tar)
    if print_content:
        proc.check_call(
            ['find', basename, '-type', 'f', '-exec', 'ls', '-lhS', '{}', '+'],
            cwd=up_directory)
    proc.check_call(['tar', 'cjf', tar, basename], cwd=up_directory)
    proc.check_call(['ls', '-lh', tar], cwd=up_directory)
    return tar


def Zip(directory, print_content=False):
    assert os.path.isdir(directory), 'Must be a directory'
    dirname, basename = os.path.split(directory)
    archive = os.path.join(dirname, basename + '.zip')
    print('Creating zip archive', archive)
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(directory):
            for name in files:
                fs_path = os.path.join(root, name)
                zip_path = os.path.relpath(fs_path, os.path.dirname(directory))
                if print_content:
                    print('Adding', fs_path)
                z.write(fs_path, zip_path)
    print('Size:', os.stat(archive).st_size)
    return archive


def UploadFile(local_name, remote_name):
    """Archive the file with the given name, and with the LLVM git hash."""
    if not buildbot.IsUploadingBot():
        return
    buildbot.Link(
        'download',
        cloud.Upload(
            local_name, '%s/%s/%s' %
            (buildbot.BuilderName(), buildbot.BuildNumber(), remote_name)))


def UploadArchive(name, archive):
    """Archive the tar/zip file with the given name and the build number."""
    if not buildbot.IsUploadingBot():
        return
    extension = os.path.splitext(archive)[1]
    UploadFile(archive, 'wasm-%s%s' % (name, extension))


# Repo and subproject utilities


def GitRemoteUrl(cwd, remote):
    """Get the URL of a remote."""
    return proc.check_output(
        ['git', 'config', '--get', 'remote.%s.url' % remote],
        cwd=cwd).strip()


def RemoteBranch(branch):
    """Get the remote-qualified branch name to use for waterfall"""
    return WATERFALL_REMOTE + '/' + branch


def GitUpdateRemote(src_dir, git_repo, remote_name):
    try:
        proc.check_call(['git', 'remote', 'set-url', remote_name, git_repo],
                        cwd=src_dir)
    except proc.CalledProcessError:
        # If proc.check_call fails it throws an exception. 'git remote set-url'
        # fails when the remote doesn't exist, so we should try to add it.
        proc.check_call(['git', 'remote', 'add', remote_name, git_repo],
                        cwd=src_dir)


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
            raise Exception(
                'Filter cannot include both include and exclude rules')

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
                            'Valid {1} steps:\n{2}'.format(
                                missing_names, self.name,
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


class Source(object):
    """Metadata about a sync-able source repo on the waterfall"""
    def __init__(self, name, src_dir, git_repo,
                 checkout=RemoteBranch('master'), depth=None,
                 custom_sync=None, os_filter=None):
        self.name = name
        self.src_dir = src_dir
        self.git_repo = git_repo
        self.checkout = checkout
        self.depth = depth
        self.custom_sync = custom_sync
        self.os_filter = os_filter

        # Ensure that git URLs end in .git.  We have had issues in the past
        # where github would not recognize the requests correctly otherwise due
        # to chromium's builders setting custom GIT_USER_AGENT:
        # https://bugs.chromium.org/p/chromium/issues/detail?id=711775
        if git_repo:
            assert git_repo.endswith('.git'), 'Git URLs should end in .git'

    def Sync(self, good_hashes=None):
        if self.os_filter and not self.os_filter.Check(BuilderPlatformName()):
            print("Skipping %s: Doesn't work on %s" %
                  (self.name, BuilderPlatformName()))
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
            print('%s directory already exists' % self.name)
        else:
            clone = ['clone', self.git_repo, self.src_dir]
            if self.depth:
                clone.append('--depth')
                clone.append(str(self.depth))
            proc.check_call(['git'] + clone)

        GitUpdateRemote(self.src_dir, self.git_repo, WATERFALL_REMOTE)
        proc.check_call(['git', 'fetch', '--force', '--prune', '--tags',
                         WATERFALL_REMOTE],
                        cwd=self.src_dir)
        if not self.checkout.startswith(WATERFALL_REMOTE + '/'):
            sys.stderr.write(
                ('WARNING: `git checkout %s` not based on waterfall '
                 'remote (%s), checking out local branch' %
                 (self.checkout, WATERFALL_REMOTE)))
        proc.check_call(['git', 'checkout', self.checkout], cwd=self.src_dir)
        proc.check_call(['git', 'submodule', 'update', '--init'],
                        cwd=self.src_dir)

    def CurrentGitInfo(self):
        if not os.path.exists(self.src_dir):
            return None

        def pretty(fmt):
            return proc.check_output(
                ['git', 'log', '-n1',
                 '--pretty=format:%s' % fmt],
                cwd=self.src_dir).strip()

        try:
            remote = GitRemoteUrl(self.src_dir, WATERFALL_REMOTE)
        except proc.CalledProcessError:
            # Not all checkouts have the '_waterfall' remote (e.g. the
            # waterfall itself) so fall back to origin on failure
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
        print('<<<<<<<<<< STATUS FOR', self.name, '>>>>>>>>>>')
        if os.path.exists(self.src_dir):
            proc.check_call(['git', 'status'], cwd=self.src_dir)
        print()


def ChromiumFetchSync(name, work_dir, git_repo,
                      checkout=RemoteBranch('master')):
    """Some Chromium projects want to use gclient for clone and
    dependencies."""
    if os.path.isdir(work_dir):
        print('%s directory already exists' % name)
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
        host_toolchains.SyncPrebuiltClang(src_dir)
        cc = GetPrebuiltClang('clang')
        cxx = GetPrebuiltClang('clang++')
        assert os.path.isfile(cc), 'Expect clang at %s' % cc
        assert os.path.isfile(cxx), 'Expect clang++ at %s' % cxx


def SyncArchive(out_dir, name, url, create_out_dir=False):
    """Download and extract an archive (zip, tar.gz or tar.xz) file from a URL.

    The extraction happens in the prebuilt dir. If create_out_dir is True,
    out_dir will be created and the archive will be extracted inside. Otherwise
    the archive is expected to contain a top-level directory with all the
    files; this is expected to be 'out_dir', so if 'out_dir' already exists
    then the download will be skipped.
    """
    stamp_file = os.path.join(out_dir, 'stamp.txt')
    if os.path.isdir(out_dir):
        if os.path.isfile(stamp_file):
            with open(stamp_file) as f:
                stamp_url = f.read().strip()
            if stamp_url == url:
                print('%s directory already exists' % name)
                return
        print('%s directory exists but is not up-to-date' % name)
    print('Downloading %s from %s' % (name, url))

    if create_out_dir:
        os.makedirs(out_dir)
        work_dir = out_dir
    else:
        work_dir = os.path.dirname(out_dir)

    try:
        f = urlopen(url)
        print('URL: %s' % f.geturl())
        print('Info: %s' % f.info())
        with tempfile.NamedTemporaryFile() as t:
            t.write(f.read())
            t.flush()
            t.seek(0)
            print('Extracting into %s' % work_dir)
            ext = os.path.splitext(url)[-1]
            if ext == '.zip':
                with zipfile.ZipFile(t, 'r') as zip:
                    zip.extractall(path=work_dir)
            elif ext == '.xz':
                proc.check_call(['tar', '-xf', t.name], cwd=work_dir)
            else:
                tarfile.open(fileobj=t).extractall(path=work_dir)
    except URLError as e:
        print('Error downloading %s: %s' % (url, e))
        raise

    with open(stamp_file, 'w') as f:
        f.write(url + '\n')


def SyncPrebuiltCMake(name, src_dir, git_repo):
    extension = '.zip' if IsWindows() else '.tar.gz'
    url = WASM_STORAGE_BASE + PREBUILT_CMAKE_BASE_NAME + extension
    SyncArchive(PrebuiltCMakeDir(), 'cmake', url)


def SyncPrebuiltNodeJS(name, src_dir, git_repo):
    extension = {
        'darwin': 'tar.xz',
        'linux': 'tar.xz',
        'win32': 'zip'
    }[sys.platform]
    out_dir = GetPrebuilt(NODE_BASE_NAME + NodePlatformName())
    tarball = NODE_BASE_NAME + NodePlatformName() + '.' + extension
    node_url = WASM_STORAGE_BASE + tarball
    return SyncArchive(out_dir, name, node_url)


# Utilities needed for running LLVM regression tests on Windows
def SyncGNUWin32(name, src_dir, git_repo):
    if not IsWindows():
        return
    url = WASM_STORAGE_BASE + GNUWIN32_ZIP
    return SyncArchive(GetPrebuilt('gnuwin32'), name, url)


def SyncPrebuiltJava(name, src_dir, git_repo):
    platform = {
        'linux': 'linux',
        'linux2': 'linux',
        'darwin': 'osx',
        'win32': 'windows'
    }[sys.platform]
    tarball = 'jre-' + JAVA_VERSION + '_' + platform + '-x64_bin.tar.gz'
    java_url = WASM_STORAGE_BASE + tarball
    SyncArchive(JavaDir(), name, java_url)


def SyncLinuxSysroot(name, src_dir, git_repo):
    if not (IsLinux() and host_toolchains.ShouldUseSysroot()):
        return
    SyncArchive(GetPrebuilt(LINUX_SYSROOT),
                name,
                LINUX_SYSROOT_URL,
                create_out_dir=True)


def NoSync(*args):
    pass


def AllSources():
    return [
        Source('waterfall', SCRIPT_DIR, None, custom_sync=NoSync),
        Source('llvm', GetSrcDir('llvm-project'),
               LLVM_GIT_BASE + 'llvm-project.git'),
        Source('llvm-test-suite', GetSrcDir('llvm-test-suite'),
               LLVM_GIT_BASE + 'llvm-test-suite.git'),
        Source('emscripten', GetSrcDir('emscripten'),
               EMSCRIPTEN_GIT_BASE + 'emscripten.git'),
        Source('gcc', GetSrcDir('gcc'),
               GIT_MIRROR_BASE + 'chromiumos/third_party/gcc.git',
               checkout=GCC_REVISION, depth=GCC_CLONE_DEPTH),
        Source('v8', work_dirs.GetV8(), GIT_MIRROR_BASE + 'v8/v8.git',
               custom_sync=ChromiumFetchSync),
        Source('host-toolchain', work_dirs.GetV8(), '',
               custom_sync=SyncToolchain),
        Source('cmake', '', '',  # The source and git args are ignored.
               custom_sync=SyncPrebuiltCMake),
        Source('nodejs', '', '',  # The source and git args are ignored.
               custom_sync=SyncPrebuiltNodeJS),
        Source('gnuwin32', '', '',  # The source and git args are ignored.
               custom_sync=SyncGNUWin32),
        Source('wabt', GetSrcDir('wabt'), WASM_GIT_BASE + 'wabt.git'),
        Source('binaryen', GetSrcDir('binaryen'),
               WASM_GIT_BASE + 'binaryen.git'),
        Source('wasi-libc', GetSrcDir('wasi-libc'),
               'https://github.com/CraneStation/wasi-libc.git'),
        Source('java', '', '',  # The source and git args are ignored.
               custom_sync=SyncPrebuiltJava),
        Source('sysroot', '', '',  # The source and git args are ignored.
               custom_sync=SyncLinuxSysroot)
    ]


def Clobber():
    # Don't automatically clobber non-bot (local) work directories
    if not buildbot.IsBot() and not options.clobber:
        return

    clobber = options.clobber or buildbot.ShouldClobber()
    clobber_file = GetBuildDir('clobber_version.txt')
    if not clobber:
        if not os.path.exists(clobber_file):
            print('Clobber file %s does not exist.' % clobber_file)
            clobber = True
        else:
            existing_tag = int(open(clobber_file).read().strip())
            if existing_tag != CLOBBER_BUILD_TAG:
                print('Clobber file %s has tag %s.' %
                      (clobber_file, existing_tag))
                clobber = True

    if not clobber:
        return

    buildbot.Step('Clobbering work dir')
    if buildbot.IsEmscriptenReleasesBot() or not buildbot.IsBot():
        # Never clear source dirs locally.
        # On emscripten-releases, depot_tools and the recipe clear the rest.
        dirs = [work_dirs.GetBuild()]
    else:
        dirs = work_dirs.GetAll()
    for work_dir in dirs:
        Remove(work_dir)
        Mkdir(work_dir)
    # Also clobber v8
    v8_dir = os.path.join(work_dirs.GetV8(), V8_BUILD_SUBDIR)
    Remove(v8_dir)
    with open(clobber_file, 'w') as f:
        f.write('%s\n' % CLOBBER_BUILD_TAG)


def SyncRepos(filter, sync_lkgr=False):
    if not filter.Any():
        return
    buildbot.Step('Sync Repos')

    good_hashes = None
    if sync_lkgr:
        lkgr_file = GetBuildDir('lkgr.json')
        cloud.Download('%s/lkgr.json' % BuilderPlatformName(), lkgr_file)
        lkgr = json.loads(open(lkgr_file).read())
        good_hashes = {}
        for k, v in lkgr['repositories'].iteritems():
            good_hashes[k] = v.get('hash') if v else None

    for repo in filter.Apply(AllSources()):
        repo.Sync(good_hashes)


def GetRepoInfo():
    """Collect a readable form of all repo information here, preventing the
  summary from getting out of sync with the actual list of repos."""
    info = {}
    for r in AllSources():
        info[r.name] = r.CurrentGitInfo()
    return info


# Build rules

def OverrideCMakeCompiler():
    if not host_toolchains.ShouldForceHostClang():
        return []
    cc = 'clang-cl' if IsWindows() else 'clang'
    cxx = 'clang-cl' if IsWindows() else 'clang++'
    return [
        '-DCMAKE_C_COMPILER=' + Executable(GetPrebuiltClang(cc)),
        '-DCMAKE_CXX_COMPILER=' + Executable(GetPrebuiltClang(cxx))
    ]


def CMakeCommandBase():
    command = [PrebuiltCMakeBin(), '-G', 'Ninja']
    # Python's location could change, so always update CMake's cache
    command.append('-DPYTHON_EXECUTABLE=%s' % sys.executable)
    command.append('-DCMAKE_EXPORT_COMPILE_COMMANDS=ON')
    command.append('-DCMAKE_BUILD_TYPE=Release')
    if IsMac():
        # Target MacOS Sierra (10.12)
        command.append('-DCMAKE_OSX_DEPLOYMENT_TARGET=10.12')
    elif IsWindows():
        # CMake's usual logic fails to find LUCI's git on Windows
        git_exe = proc.Which('git')
        command.append('-DGIT_EXECUTABLE=%s' % git_exe)
    return command


def CMakeCommandNative(args, build_dir):
    command = CMakeCommandBase()
    command.append('-DCMAKE_INSTALL_PREFIX=%s' % GetInstallDir())
    if IsLinux() and host_toolchains.ShouldUseSysroot():
        command.append('-DCMAKE_SYSROOT=%s' % GetPrebuilt(LINUX_SYSROOT))
        command.append('-DCMAKE_EXE_LINKER_FLAGS=-static-libstdc++')
        command.append('-DCMAKE_SHARED_LINKER_FLAGS=-static-libstdc++')

    elif IsMac() and host_toolchains.ShouldUseSysroot():
        # Get XCode SDK path.
        xcode_sdk_path = proc.check_output(['xcrun',
                                            '--show-sdk-path']).strip()
        # Create relpath symlink if it doesn't exist.
        # If it does exist, but points to a different location, update it.
        symlink_path = os.path.join(build_dir, 'xcode_sdk')
        if os.path.lexists(
                symlink_path) and os.readlink(symlink_path) != xcode_sdk_path:
            os.remove(symlink_path)
        if not os.path.exists(symlink_path):
            os.symlink(xcode_sdk_path, symlink_path)
        command.append('-DCMAKE_OSX_SYSROOT=%s' % symlink_path)
        command.append('-DCMAKE_SYSROOT=%s' % symlink_path)

    if host_toolchains.ShouldForceHostClang():
        command.extend(OverrideCMakeCompiler())
        # Goma doesn't have MSVC in its cache, so don't use it in this case
        command.extend(host_toolchains.CMakeLauncherFlags())
    command.extend(args)
    # On Windows, CMake chokes on paths containing backslashes that come from
    # the command line. Probably they just need to be escaped, but using '/'
    # instead is easier and works just as well.
    return [arg.replace('\\', '/') for arg in command]


def CMakeCommandWasi(args):
    command = CMakeCommandBase()
    command.append('-DCMAKE_TOOLCHAIN_FILE=%s' %
                   GetInstallDir(CMAKE_TOOLCHAIN_FILE))
    command.extend(args)
    return command


def CopyLLVMTools(build_dir, prefix=''):
    # The following aren't useful for now, and take up space.
    # DLLs are in bin/ on Windows but in lib/ on posix.
    for unneeded_tool in ('clang-check', 'clang-cl', 'clang-cpp',
                          'clang-extdef-mapping', 'clang-format',
                          'clang-func-mapping', 'clang-import-test',
                          'clang-offload-bundler', 'clang-refactor',
                          'clang-rename', 'clang-scan-deps', 'libclang.dll',
                          'lld-link', 'ld.lld', 'lld64.lld', 'llvm-lib'):
        Remove(GetInstallDir(prefix, 'bin', Executable(unneeded_tool)))

    for lib in ['libclang.%s' for suffix in ('so.*', 'dylib')]:
        Remove(GetInstallDir(prefix, 'lib', lib))

    # The following are useful, LLVM_INSTALL_TOOLCHAIN_ONLY did away with them.
    extra_bins = map(Executable, [
        'FileCheck', 'llc', 'llvm-as', 'llvm-dis', 'llvm-link', 'llvm-mc',
        'llvm-nm', 'llvm-objdump', 'llvm-readobj', 'llvm-size', 'opt',
        'llvm-dwarfdump'
    ])
    for p in [
            glob.glob(os.path.join(build_dir, 'bin', b)) for b in extra_bins
    ]:
        for e in p:
            CopyBinaryToArchive(os.path.join(build_dir, 'bin', e), prefix)


def BuildEnv(build_dir, use_gnuwin32=False, bin_subdir=False,
             runtime='Release'):
    if not IsWindows():
        return None
    cc_env = host_toolchains.SetUpVSEnv(build_dir)
    if use_gnuwin32:
        cc_env['PATH'] = cc_env['PATH'] + os.pathsep + GetSrcDir(
            'gnuwin32', 'bin')
    bin_dir = build_dir if not bin_subdir else os.path.join(build_dir, 'bin')
    Mkdir(bin_dir)
    assert runtime in ['Release', 'Debug']
    host_toolchains.CopyDlls(bin_dir, runtime)
    return cc_env


def LLVM():
    buildbot.Step('LLVM')
    build_dir = os.path.join(work_dirs.GetBuild(), 'llvm-out')
    Mkdir(build_dir)
    cc_env = BuildEnv(build_dir, bin_subdir=True)
    build_dylib = 'ON' if not IsWindows() else 'OFF'
    command = CMakeCommandNative([
        GetLLVMSrcDir('llvm'),
        '-DCMAKE_CXX_FLAGS=-Wno-nonportable-include-path',
        '-DLLVM_ENABLE_LIBXML2=OFF',
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
        '-DLLVM_TARGETS_TO_BUILD=X86;WebAssembly',
        '-DLLVM_ENABLE_PROJECTS=lld;clang',
        # linking libtinfo dynamically causes problems on some linuxes,
        # https://github.com/emscripten-core/emsdk/issues/252
        '-DLLVM_ENABLE_TERMINFO=%d' % (not IsLinux()),
    ], build_dir)

    jobs = host_toolchains.NinjaJobs()

    proc.check_call(command, cwd=build_dir, env=cc_env)
    proc.check_call(['ninja', '-v'] + jobs, cwd=build_dir, env=cc_env)
    proc.check_call(['ninja', 'install'] + jobs, cwd=build_dir, env=cc_env)
    CopyLLVMTools(build_dir)
    install_bin = GetInstallDir('bin')
    for target in ('clang', 'clang++'):
        for link in 'wasm32-', 'wasm32-wasi-':
            link = os.path.join(install_bin, link + target)
            if not IsWindows():
                if not os.path.islink(Executable(link)):
                    os.symlink(Executable(target), Executable(link))
            else:
                # Windows has no symlinks (at least not from python). Also
                # clang won't work as a native compiler anyway, so just install
                # it as wasm32-wasi-clang
                shutil.copy2(Executable(os.path.join(install_bin, target)),
                             Executable(link))


def LLVMTestDepends():
    buildbot.Step('LLVM Test Dependencies')
    build_dir = os.path.join(work_dirs.GetBuild(), 'llvm-out')
    proc.check_call(['ninja', '-v', 'test-depends'] +
                    host_toolchains.NinjaJobs(),
                    cwd=build_dir,
                    env=BuildEnv(build_dir, bin_subdir=True))


def TestLLVMRegression():
    build_dir = os.path.join(work_dirs.GetBuild(), 'llvm-out')
    cc_env = BuildEnv(build_dir, bin_subdir=True)
    if not os.path.isdir(build_dir):
        print('LLVM Build dir %s does not exist' % build_dir)
        buildbot.Fail()
        return

    def RunWithUnixUtils(cmd, **kwargs):
        if IsWindows():
            return proc.check_call(['git', 'bash'] + cmd, **kwargs)
        else:
            return proc.check_call(cmd, **kwargs)

    try:
        buildbot.Step('LLVM regression tests')
        RunWithUnixUtils(['ninja', 'check-all'], cwd=build_dir, env=cc_env)
    except proc.CalledProcessError:
        buildbot.FailUnless(lambda: IsWindows())


def V8():
    buildbot.Step('V8')
    src_dir = work_dirs.GetV8()
    out_dir = os.path.join(src_dir, V8_BUILD_SUBDIR)
    vpython = 'vpython' + ('.bat' if IsWindows() else '')

    # Generate and write a GN args file.
    gn_args = 'is_debug = false\ntarget_cpu = "x64"\n'
    if host_toolchains.UsingGoma():
        gn_args += 'use_goma = true\n'
        gn_args += 'goma_dir = "%s"\n' % host_toolchains.GomaDir()
    Mkdir(out_dir)
    with open(os.path.join(out_dir, 'args.gn'), 'w') as f:
        f.write(gn_args)
    # Invoke GN to generate. We need to use vpython as the script interpreter
    # since GN's scripts seem to require python2. Hence we need to invoke GN
    # directly rather than using one of V8's GN wrapper scripts (e.g. mb.py).
    # But because V8 has a different directory layout from Chrome, we can't
    # just use the GN wrapper in depot_tools, we have to invoke the one in the
    # V8 buildtools dir directly.
    gn_platform = 'linux64' if IsLinux() else 'mac' if IsMac() else 'win'
    gn_exe = Executable(os.path.join(src_dir, 'buildtools', gn_platform, 'gn'))
    proc.check_call([gn_exe, 'gen', out_dir, '--script-executable=' + vpython],
                    cwd=src_dir)

    jobs = host_toolchains.NinjaJobs()
    proc.check_call(['ninja', '-v', '-C', out_dir, 'd8', 'unittests'] + jobs,
                    cwd=src_dir)
    # Copy the V8 snapshot as well as the ICU data file for timezone data.
    # icudtl.dat is the little-endian version, which goes with x64.
    to_archive = [Executable('d8'), 'snapshot_blob.bin', 'icudtl.dat']
    for a in to_archive:
        CopyBinaryToArchive(os.path.join(out_dir, a))


def Jsvu():
    buildbot.Step('jsvu')
    jsvu_dir = os.path.join(work_dirs.GetBuild(), 'jsvu')
    Mkdir(jsvu_dir)

    if IsWindows():
        # jsvu OS identifiers:
        # https://github.com/GoogleChromeLabs/jsvu#supported-engines
        os_id = 'windows64'
        js_engines = 'chakra'
    elif IsMac():
        os_id = 'mac64'
        js_engines = 'javascriptcore,v8'
    else:
        os_id = 'linux64'
        js_engines = 'javascriptcore'

    try:
        # https://github.com/GoogleChromeLabs/jsvu#installation
        # ...except we install it locally instead of globally.
        proc.check_call(['npm', 'install', 'jsvu'], cwd=jsvu_dir)

        jsvu_bin = Executable(
            os.path.join(jsvu_dir, 'node_modules', 'jsvu', 'cli.js'))
        # https://github.com/GoogleChromeLabs/jsvu#integration-with-non-interactive-environments
        proc.check_call(
            [jsvu_bin,
             '--os=%s' % os_id,
             '--engines=%s' % js_engines])

        # $HOME/.jsvu/chakra is now available on Windows.
        # $HOME/.jsvu/javascriptcore is now available on Mac.

        # TODO: Install the JSC binary in the output package, and add the
        # version info to the repo info JSON file (currently in GetRepoInfo)
    except proc.CalledProcessError:
        buildbot.Warn()


def Wabt():
    buildbot.Step('WABT')
    out_dir = os.path.join(work_dirs.GetBuild(), 'wabt-out')
    Mkdir(out_dir)
    cc_env = BuildEnv(out_dir)

    cmd = CMakeCommandNative([GetSrcDir('wabt'),
                              '-DBUILD_TESTS=OFF', '-DBUILD_LIBWASM=OFF'],
                             out_dir)
    proc.check_call(cmd, cwd=out_dir, env=cc_env)

    proc.check_call(['ninja', '-v'] + host_toolchains.NinjaJobs(),
                    cwd=out_dir,
                    env=cc_env)
    proc.check_call(['ninja', 'install'], cwd=out_dir, env=cc_env)


def Binaryen():
    buildbot.Step('binaryen')
    out_dir = os.path.join(work_dirs.GetBuild(), 'binaryen-out')
    Mkdir(out_dir)
    # Currently it's a bad idea to do a non-asserts build of Binaryen
    cc_env = BuildEnv(out_dir, bin_subdir=True, runtime='Debug')

    proc.check_call(CMakeCommandNative([GetSrcDir('binaryen')], out_dir),
                    cwd=out_dir,
                    env=cc_env)
    proc.check_call(['ninja', '-v'] + host_toolchains.NinjaJobs(),
                    cwd=out_dir,
                    env=cc_env)
    proc.check_call(['ninja', 'install'], cwd=out_dir, env=cc_env)


def InstallEmscripten():
    src_dir = GetSrcDir('emscripten')
    em_install_dir = GetInstallDir('emscripten')
    Remove(em_install_dir)
    print('Installing emscripten into %s' % em_install_dir)
    proc.check_call([os.path.join('tools', 'install.py'), em_install_dir],
                    cwd=src_dir)

    print('Running npm install ...')
    proc.check_call(['npm', 'ci', '--no-optional'], cwd=em_install_dir)

    # Manually install the appropriate native Closure Compiler package
    # This is currently needed because npm ci will install the packages
    # for Closure for all platforms, adding 180MB to the download size
    # There are two problems here:
    #   1. npm ci does not consider the platform of optional dependencies
    #      https://github.com/npm/cli/issues/558
    #   2. A bug with the native compiler has bloated the packages from
    #      30MB to almost 300MB
    #      https://github.com/google/closure-compiler-npm/issues/186
    # If either of these bugs are fixed we could consider removing this
    # hack.
    native = None
    if IsMac():
        native = 'google-closure-compiler-osx'
    elif IsWindows():
        native = 'google-closure-compiler-windows'
    elif IsLinux():
        native = 'google-closure-compiler-linux'
    proc.check_call(['npm', 'install', native], cwd=em_install_dir)


def Emscripten():
    InstallEmscripten()

    def WriteEmscriptenConfig(infile, outfile):
        with open(infile) as config:
            text = config.read().replace('{{WASM_INSTALL}}',
                                         WindowsFSEscape(GetInstallDir()))
            text = text.replace('{{PREBUILT_NODE}}',
                                WindowsFSEscape(NodeBin()))
            text = text.replace('{{PREBUILT_JAVA}}',
                                WindowsFSEscape(JavaBin()))
        with open(outfile, 'w') as config:
            config.write(text)

    # Set up the emscripten config and compile the libraries
    buildbot.Step('emscripten')
    config = GetInstallDir(EMSCRIPTEN_CONFIG_UPSTREAM)
    print('Config file: ', config)
    src_config = os.path.join(SCRIPT_DIR, os.path.basename(config))
    WriteEmscriptenConfig(src_config, config)

    env = os.environ.copy()
    env['EM_CONFIG'] = config
    try:
        # Use emscripten's embuilder to prebuild the system libraries.
        # This depends on binaryen already being built and installed into the
        # archive/install dir.
        proc.check_call([
            sys.executable,
            os.path.join(GetInstallDir('emscripten'), 'embuilder.py'), 'build',
            'SYSTEM'
        ], env=env)

    except proc.CalledProcessError:
        # Note the failure but allow the build to continue.
        buildbot.Fail()

    # Remove the sanity file.  This means it will get generated on first
    # use without clearing the cache.
    sanity = GetInstallDir('emscripten', 'cache', 'sanity.txt')
    if os.path.exists(sanity):
        os.remove(sanity)


def CompilerRT():
    # TODO(sbc): Figure out how to do this step as part of the llvm build.
    # I suspect that this can be done using the llvm/runtimes directory but
    # have yet to make it actually work this way.
    buildbot.Step('compiler-rt')

    build_dir = os.path.join(work_dirs.GetBuild(), 'compiler-rt-out')
    # TODO(sbc): Remove this.
    # The compiler-rt doesn't currently rebuild libraries when a new -DCMAKE_AR
    # value is specified.
    if os.path.isdir(build_dir):
        Remove(build_dir)

    Mkdir(build_dir)
    src_dir = GetLLVMSrcDir('compiler-rt')
    cc_env = BuildEnv(src_dir, bin_subdir=True)
    command = CMakeCommandWasi([
        os.path.join(src_dir, 'lib', 'builtins'),
        '-DCMAKE_C_COMPILER_WORKS=ON', '-DCOMPILER_RT_BAREMETAL_BUILD=On',
        '-DCOMPILER_RT_BUILD_XRAY=OFF', '-DCOMPILER_RT_INCLUDE_TESTS=OFF',
        '-DCOMPILER_RT_ENABLE_IOS=OFF', '-DCOMPILER_RT_DEFAULT_TARGET_ONLY=On',
        '-DLLVM_CONFIG_PATH=' + Executable(
            os.path.join(work_dirs.GetBuild(), 'llvm-out', 'bin',
                         'llvm-config')),
        '-DCMAKE_INSTALL_PREFIX=' + GetInstallDir('lib', 'clang', LLVM_VERSION)
    ])

    proc.check_call(command, cwd=build_dir, env=cc_env)
    proc.check_call(['ninja', '-v'], cwd=build_dir, env=cc_env)
    proc.check_call(['ninja', 'install'], cwd=build_dir, env=cc_env)


def LibCXX():
    buildbot.Step('libcxx')
    build_dir = os.path.join(work_dirs.GetBuild(), 'libcxx-out')
    if os.path.isdir(build_dir):
        Remove(build_dir)
    Mkdir(build_dir)
    src_dir = GetLLVMSrcDir('libcxx')
    cc_env = BuildEnv(src_dir, bin_subdir=True)
    command = CMakeCommandWasi([
        src_dir,
        '-DCMAKE_EXE_LINKER_FLAGS=-nostdlib++',
        '-DLIBCXX_ENABLE_THREADS=OFF',
        '-DLIBCXX_ENABLE_SHARED=OFF',
        '-DLIBCXX_ENABLE_FILESYSTEM=OFF',
        '-DLIBCXX_HAS_MUSL_LIBC=ON',
        '-DLIBCXX_CXX_ABI=libcxxabi',
        '-DLIBCXX_LIBDIR_SUFFIX=/wasm32-wasi',
        '-DLIBCXX_CXX_ABI_INCLUDE_PATHS=' +
        GetLLVMSrcDir('libcxxabi', 'include'),
        '-DLLVM_PATH=' + GetLLVMSrcDir('llvm'),
    ])

    proc.check_call(command, cwd=build_dir, env=cc_env)
    proc.check_call(['ninja', '-v'], cwd=build_dir, env=cc_env)
    proc.check_call(['ninja', 'install'], cwd=build_dir, env=cc_env)


def LibCXXABI():
    buildbot.Step('libcxxabi')
    build_dir = os.path.join(work_dirs.GetBuild(), 'libcxxabi-out')
    if os.path.isdir(build_dir):
        Remove(build_dir)
    Mkdir(build_dir)
    src_dir = GetLLVMSrcDir('libcxxabi')
    cc_env = BuildEnv(src_dir, bin_subdir=True)
    command = CMakeCommandWasi([
        src_dir,
        '-DCMAKE_EXE_LINKER_FLAGS=-nostdlib++',
        '-DLIBCXXABI_ENABLE_PIC=OFF',
        '-DLIBCXXABI_ENABLE_SHARED=OFF',
        '-DLIBCXXABI_ENABLE_THREADS=OFF',
        '-DLIBCXXABI_LIBDIR_SUFFIX=/wasm32-wasi',
        '-DLIBCXXABI_LIBCXX_PATH=' + GetLLVMSrcDir('libcxx'),
        '-DLIBCXXABI_LIBCXX_INCLUDES=' +
        GetInstallDir('sysroot', 'include', 'c++', 'v1'),
        '-DLLVM_PATH=' + GetLLVMSrcDir('llvm'),
    ])

    proc.check_call(command, cwd=build_dir, env=cc_env)
    proc.check_call(['ninja', '-v'], cwd=build_dir, env=cc_env)
    proc.check_call(['ninja', 'install'], cwd=build_dir, env=cc_env)
    CopyLibraryToSysroot(os.path.join(SCRIPT_DIR, 'libc++abi.imports'))


def WasiLibc():
    buildbot.Step('Wasi')
    build_dir = os.path.join(work_dirs.GetBuild(), 'wasi-libc-out')
    if os.path.isdir(build_dir):
        Remove(build_dir)
    cc_env = BuildEnv(build_dir, use_gnuwin32=True)
    src_dir = GetSrcDir('wasi-libc')
    cmd = [
        proc.Which('make'),
        '-j%s' % NPROC, 'SYSROOT=' + build_dir,
        'WASM_CC=' + GetInstallDir('bin', 'clang')
    ]
    proc.check_call(cmd, env=cc_env, cwd=src_dir)
    CopyTree(build_dir, GetInstallDir('sysroot'))

    # We add the cmake toolchain file and out JS polyfill script to make using
    # the wasi toolchain easier.
    shutil.copy2(os.path.join(SCRIPT_DIR, CMAKE_TOOLCHAIN_FILE),
                 GetInstallDir(CMAKE_TOOLCHAIN_FILE))
    Remove(GetInstallDir('cmake'))
    shutil.copytree(os.path.join(SCRIPT_DIR, 'cmake'), GetInstallDir('cmake'))

    shutil.copy2(os.path.join(SCRIPT_DIR, 'wasi.js'), GetInstallDir())


def ArchiveBinaries():
    buildbot.Step('Archive binaries')
    archive = Archive(GetInstallDir(), print_content=buildbot.IsBot())
    if not buildbot.IsUploadingBot():
        return
    # All relevant binaries were copied to the LLVM directory.
    UploadArchive('binaries', archive)


def DebianPackage():
    if not (IsLinux() and buildbot.IsBot()):
        return

    buildbot.Step('Debian package')
    top_dir = os.path.dirname(SCRIPT_DIR)
    try:
        if buildbot.BuildNumber():
            message = ('Automatic build %s produced on http://wasm-stat.us' %
                       buildbot.BuildNumber())
            version = '0.1.' + buildbot.BuildNumber()
            proc.check_call(['dch', '-D', 'unstable', '-v', version, message],
                            cwd=top_dir)
        proc.check_call(['debuild', '--no-lintian', '-i', '-us', '-uc', '-b'],
                        cwd=top_dir)
        if buildbot.BuildNumber():
            proc.check_call(['git', 'checkout', 'debian/changelog'],
                            cwd=top_dir)

            debfile = os.path.join(os.path.dirname(top_dir),
                                   'wasm-toolchain_%s_amd64.deb' % version)
            UploadFile(debfile, os.path.basename(debfile))
    except proc.CalledProcessError:
        # Note the failure but allow the build to continue.
        buildbot.Fail()
        return


def CompileLLVMTorture(outdir, opt):
    name = 'Compile LLVM Torture (%s)' % opt
    buildbot.Step(name)
    install_bin = GetInstallDir('bin')
    cc = Executable(os.path.join(install_bin, 'wasm32-wasi-clang'))
    cxx = Executable(os.path.join(install_bin, 'wasm32-wasi-clang++'))
    Remove(outdir)
    Mkdir(outdir)
    unexpected_result_count = compile_torture_tests.run(
        cc=cc,
        cxx=cxx,
        testsuite=GccTestDir(),
        sysroot_dir=GetInstallDir('sysroot'),
        fails=[
            GetLLVMSrcDir('llvm', 'lib', 'Target', 'WebAssembly', IT_IS_KNOWN)
        ],
        exclusions=LLVM_TORTURE_EXCLUSIONS,
        out=outdir,
        config='clang',
        opt=opt)
    if 0 != unexpected_result_count:
        buildbot.Fail()


def CompileLLVMTortureEmscripten(name, em_config, outdir, fails, opt):
    buildbot.Step('Compile LLVM Torture (%s, %s)' % (name, opt))
    cc = Executable(GetInstallDir('emscripten', 'emcc'), '.bat')
    cxx = Executable(GetInstallDir('emscripten', 'em++'), '.bat')
    Remove(outdir)
    Mkdir(outdir)
    os.environ['EM_CONFIG'] = em_config
    unexpected_result_count = compile_torture_tests.run(
        cc=cc,
        cxx=cxx,
        testsuite=GccTestDir(),
        sysroot_dir=GetInstallDir('sysroot'),
        fails=fails,
        exclusions=LLVM_TORTURE_EXCLUSIONS,
        out=outdir,
        config='emscripten',
        opt=opt)

    if 0 != unexpected_result_count:
        buildbot.Fail()


def LinkLLVMTorture(name, linker, fails, indir, outdir, extension,
                    opt, args=None):
    buildbot.Step('Link LLVM Torture (%s, %s)' % (name, opt))
    assert os.path.isfile(linker), 'Cannot find linker at %s' % linker
    Remove(outdir)
    Mkdir(outdir)
    input_pattern = os.path.join(indir, '*.' + extension)
    unexpected_result_count = link_assembly_files.run(linker=linker,
                                                      files=input_pattern,
                                                      fails=fails,
                                                      attributes=[opt],
                                                      out=outdir,
                                                      args=args)
    if 0 != unexpected_result_count:
        buildbot.Fail()


def ExecuteLLVMTorture(name, runner, indir, fails, attributes, extension, opt,
                       outdir='', wasmjs='', extra_files=None,
                       warn_only=False):
    extra_files = [] if extra_files is None else extra_files

    buildbot.Step('Execute LLVM Torture (%s, %s)' % (name, opt))
    if not indir:
        print('Step skipped: no input')
        buildbot.Warn()
        return None
    assert os.path.isfile(runner), 'Cannot find runner at %s' % runner
    files = os.path.join(indir, '*.%s' % extension)
    if len(glob.glob(files)) == 0:
        print("No files found by", files)
        buildbot.Fail()
        return
    unexpected_result_count = execute_files.run(runner=runner,
                                                files=files,
                                                fails=fails,
                                                attributes=attributes + [opt],
                                                out=outdir,
                                                wasmjs=wasmjs,
                                                extra_files=extra_files)
    if 0 != unexpected_result_count:
        buildbot.FailUnless(lambda: warn_only)


def ValidateLLVMTorture(indir, ext, opt):
    validate = Executable(os.path.join(GetInstallDir('bin'), 'wasm-validate'))
    # Object files contain a DataCount section, so enable bulk memory
    ExecuteLLVMTorture(name='validate',
                       runner=validate,
                       indir=indir,
                       fails=None,
                       attributes=[opt],
                       extension=ext,
                       opt=opt)


class Build(object):
    def __init__(self, name_, runnable_, os_filter=None, is_default=True,
                 *args, **kwargs):
        self.name = name_
        self.runnable = runnable_
        self.os_filter = os_filter
        self.is_deafult = is_default
        self.args = args
        self.kwargs = kwargs

    def Run(self):
        if self.os_filter and not self.os_filter.Check(BuilderPlatformName()):
            print("Skipping %s: Doesn't work on %s" %
                  (self.runnable.__name__, BuilderPlatformName()))
            return
        self.runnable(*self.args, **self.kwargs)


def Summary():
    buildbot.Step('Summary')

    # Emscripten-releases bots run the stages separately so LKGR has no way of
    # knowing whether everything passed or not.
    should_upload = (buildbot.IsUploadingBot() and
                     not buildbot.IsEmscriptenReleasesBot())

    if should_upload:
        info = {'repositories': GetRepoInfo()}
        info['build'] = buildbot.BuildNumber()
        info['scheduler'] = buildbot.Scheduler()
        info_file = GetInstallDir('buildinfo.json')
        info_json = json.dumps(info, indent=2)
        print(info_json)

        with open(info_file, 'w+') as f:
            f.write(info_json)
            f.write('\n')

    print('Failed steps: %s.' % buildbot.Failed())
    for step in buildbot.FailedList():
        print('    %s' % step)
    print('Warned steps: %s.' % buildbot.Warned())
    for step in buildbot.WarnedList():
        print('    %s' % step)

    if should_upload:
        latest_file = '%s/%s' % (buildbot.BuilderName(), 'latest.json')
        buildbot.Link('latest.json', cloud.Upload(info_file, latest_file))

    if buildbot.Failed():
        buildbot.Fail()
    else:
        if should_upload:
            lkgr_file = '%s/%s' % (buildbot.BuilderName(), 'lkgr.json')
            buildbot.Link('lkgr.json', cloud.Upload(info_file, lkgr_file))


def AllBuilds():
    return [
        # Host tools
        Build('llvm', LLVM),
        Build('llvm-test-depends', LLVMTestDepends),
        Build('v8', V8, os_filter=Filter(exclude=['mac'])),
        Build('jsvu', Jsvu, os_filter=Filter(exclude=['windows'])),
        Build('wabt', Wabt),
        Build('binaryen', Binaryen),
        Build('emscripten-upstream', Emscripten),
        # Target libs
        # TODO: re-enable wasi on windows, see #517
        Build('wasi-libc', WasiLibc, os_filter=Filter(exclude=['windows'])),
        Build('compiler-rt', CompilerRT,
              os_filter=Filter(exclude=['windows'])),
        Build('libcxx', LibCXX, os_filter=Filter(exclude=['windows'])),
        Build('libcxxabi', LibCXXABI, os_filter=Filter(exclude=['windows'])),
        # Archive
        Build('archive', ArchiveBinaries),
        Build('debian', DebianPackage),
    ]


# For now, just the builds used to test WASI and emscripten torture tests
# on wasm-stat.us
DEFAULT_BUILDS = [
    'llvm', 'v8', 'jsvu', 'wabt', 'binaryen',
    'emscripten-upstream', 'wasi-libc', 'compiler-rt',
    'libcxx', 'libcxxabi', 'archive'
]


def BuildRepos(filter):
    for rule in filter.Apply(AllBuilds()):
        rule.Run()


class Test(object):
    def __init__(self, name_, runnable_, os_filter=None):
        self.name = name_
        self.runnable = runnable_
        self.os_filter = os_filter

    def Test(self):
        if self.os_filter and not self.os_filter.Check(BuilderPlatformName()):
            print("Skipping %s: Doesn't work on %s" %
                  (self.name, BuilderPlatformName()))
            return
        self.runnable()


def GetTortureDir(name, opt):
    dirs = {
        'asm2wasm': GetTestDir('asm2wasm-torture-out', opt),
        'emwasm': GetTestDir('emwasm-torture-out', opt),
    }
    if name in dirs:
        return dirs[name]
    return GetTestDir('torture-' + name, opt)


def TestBare():
    # Compile
    for opt in BARE_TEST_OPT_FLAGS:
        CompileLLVMTorture(GetTortureDir('o', opt), opt)
        ValidateLLVMTorture(GetTortureDir('o', opt), 'o', opt)

    # Link/Assemble
    for opt in BARE_TEST_OPT_FLAGS:
        LinkLLVMTorture(name='lld',
                        linker=Executable(
                            GetInstallDir('bin', 'wasm32-wasi-clang++')),
                        fails=LLD_KNOWN_TORTURE_FAILURES,
                        indir=GetTortureDir('o', opt),
                        outdir=GetTortureDir('lld', opt),
                        extension='o',
                        opt=opt)

    # Execute
    common_attrs = ['bare']
    common_attrs += ['win'] if IsWindows() else ['posix']

    # Avoid d8 execution on windows because of flakiness,
    # https://bugs.chromium.org/p/v8/issues/detail?id=8211
    if not IsWindows():
        for opt in BARE_TEST_OPT_FLAGS:
            ExecuteLLVMTorture(name='d8',
                               runner=D8Bin(),
                               indir=GetTortureDir('lld', opt),
                               fails=RUN_KNOWN_TORTURE_FAILURES,
                               attributes=common_attrs + ['d8', 'lld', opt],
                               extension='wasm',
                               opt=opt,
                               wasmjs=os.path.join(SCRIPT_DIR, 'wasi.js'))

    if IsMac() and not buildbot.DidStepFailOrWarn('jsvu'):
        for opt in BARE_TEST_OPT_FLAGS:
            ExecuteLLVMTorture(name='jsc',
                               runner=os.path.join(JSVU_OUT_DIR, 'jsc'),
                               indir=GetTortureDir('lld', opt),
                               fails=RUN_KNOWN_TORTURE_FAILURES,
                               attributes=common_attrs + ['jsc', 'lld'],
                               extension='wasm',
                               opt=opt,
                               warn_only=True,
                               wasmjs=os.path.join(SCRIPT_DIR, 'wasi.js'))


def TestEmwasm():
    for opt in EMSCRIPTEN_TEST_OPT_FLAGS:
        CompileLLVMTortureEmscripten('emwasm',
                                     GetInstallDir(EMSCRIPTEN_CONFIG_UPSTREAM),
                                     GetTortureDir('emwasm', opt),
                                     EMWASM_KNOWN_TORTURE_COMPILE_FAILURES,
                                     opt)

    # Avoid d8 execution on windows because of flakiness,
    # https://bugs.chromium.org/p/v8/issues/detail?id=8211
    if not IsWindows():
        for opt in EMSCRIPTEN_TEST_OPT_FLAGS:
            ExecuteLLVMTorture(name='emwasm',
                               runner=D8Bin(),
                               indir=GetTortureDir('emwasm', opt),
                               fails=RUN_KNOWN_TORTURE_FAILURES,
                               attributes=['emwasm', 'lld', 'd8'],
                               extension='c.js',
                               opt=opt,
                               outdir=GetTortureDir('emwasm', opt))


def ExecuteEmscriptenTestSuite(name, tests, config, outdir, warn_only=False):
    buildbot.Step('Execute emscripten testsuite (%s)' % name)
    Mkdir(outdir)

    # Before we can run the tests we prepare the installed emscripten
    # directory by copying of some test data which is otherwise excluded by
    # emscripten install script (tools/install.py).
    em_install_dir = GetInstallDir('emscripten')
    installed_tests = os.path.join(em_install_dir, 'tests', 'third_party')
    if not os.path.exists(installed_tests):
        src_dir = GetSrcDir('emscripten', 'tests', 'third_party')
        print('Copying directory %s to %s' % (src_dir, em_install_dir))
        shutil.copytree(src_dir, installed_tests)

    cmd = [
        GetInstallDir('emscripten', 'tests', 'runner.py'),
        '--em-config', config
    ] + tests
    test_env = os.environ.copy()
    if buildbot.IsBot() and IsWindows():
        test_env['EMTEST_LACKS_NATIVE_CLANG'] = '1'
    try:
        proc.check_call(cmd, cwd=outdir, env=test_env)
    except proc.CalledProcessError:
        buildbot.FailUnless(lambda: warn_only)


def TestEmtest():
    tests = options.test_params if options.test_params else ['wasm2', 'other']
    ExecuteEmscriptenTestSuite('emwasm', tests,
                               GetInstallDir(EMSCRIPTEN_CONFIG_UPSTREAM),
                               os.path.join(work_dirs.GetTest(), 'emtest-out'))


def TestLLVMTestSuite():
    buildbot.Step('Execute LLVM TestSuite')

    outdir = GetBuildDir('llvmtest-out')
    # The compiler changes on every run, so incremental builds don't make
    # sense.
    Remove(outdir)
    Mkdir(outdir)
    # The C++ tests explicitly link libstdc++ for some reason, but we use
    # libc++ and it's unnecessary to link it anyway. So create an empty
    # libstdc++.a
    proc.check_call([GetInstallDir('bin', 'llvm-ar'), 'rc', 'libstdc++.a'],
                    cwd=outdir)
    # This has to be in the environment and not TEST_SUITE_EXTRA_C_FLAGS
    # because CMake doesn't append the flags to the try-compiles.
    os.environ['EM_CONFIG'] = GetInstallDir(EMSCRIPTEN_CONFIG_UPSTREAM)
    command = [GetInstallDir('emscripten', 'emcmake')] + CMakeCommandBase() + [
        GetSrcDir('llvm-test-suite'), '-DCMAKE_C_COMPILER=' +
        GetInstallDir('emscripten', 'emcc'), '-DCMAKE_CXX_COMPILER=' +
        GetInstallDir('emscripten', 'em++'), '-DTEST_SUITE_RUN_UNDER=' +
        NodeBin(), '-DTEST_SUITE_USER_MODE_EMULATION=ON',
        '-DTEST_SUITE_SUBDIRS=SingleSource',
        '-DTEST_SUITE_EXTRA_EXE_LINKER_FLAGS=' +
        '-L %s -s TOTAL_MEMORY=1024MB' % outdir,
        '-DTEST_SUITE_LLVM_SIZE=' + GetInstallDir('emscripten', 'emsize.py')
    ]

    proc.check_call(command, cwd=outdir)
    proc.check_call(['ninja', '-v'], cwd=outdir)
    results_file = 'results.json'
    lit = GetBuildDir('llvm-out', 'bin', 'llvm-lit')
    proc.call([lit, '-v', '-o', results_file, '.'], cwd=outdir)

    with open(os.path.join(outdir, results_file)) as results_fd:
        json_results = json.loads(results_fd.read())

    def get_names(code):
        # Strip the unneccessary spaces from the test name
        return [
            r['name'].replace('test-suite :: ', '')
            for r in json_results['tests'] if r['code'] == code
        ]

    failures = get_names('FAIL')
    successes = get_names('PASS')

    expected_failures = testing.parse_exclude_files(
        RUN_LLVM_TESTSUITE_FAILURES, [])
    unexpected_failures = [f for f in failures if f not in expected_failures]
    unexpected_successes = [f for f in successes if f in expected_failures]

    if len(unexpected_failures) > 0:
        print('Emscripten unexpected failures:')
        for test in unexpected_failures:
            print(test)
    if len(unexpected_successes) > 0:
        print('Emscripten unexpected successes:')
        for test in unexpected_successes:
            print(test)

    if len(unexpected_failures) + len(unexpected_successes) > 0:
        buildbot.Fail()


ALL_TESTS = [
    Test('llvm-regression', TestLLVMRegression),
    # TODO: re-enable wasi on windows, see #517
    Test('bare', TestBare, Filter(exclude=['windows'])),
    Test('emwasm', TestEmwasm, Filter(exclude=['mac'])),
    # These tests do have interesting differences on OSes (especially the
    # 'other' tests) and eventually should run everywhere.
    Test('emtest', TestEmtest),
    Test('llvmtest', TestLLVMTestSuite, Filter(include=['linux'])),
]

# The default tests to run on wasm-stat.us (just WASI and emwasm torture)
DEFAULT_TESTS = ['bare', 'emwasm', 'llvmtest']


def TextWrapNameList(prefix, items):
    width = 80  # TODO(binji): better guess?
    names = sorted(item.name for item in items)
    return '%s%s' % (prefix,
                     textwrap.fill(' '.join(names),
                                   width,
                                   initial_indent='  ',
                                   subsequent_indent='  '))


def ParseArgs():
    def SplitComma(arg):
        if not arg:
            return None
        return arg.split(',')

    epilog = '\n\n'.join([
        TextWrapNameList('sync targets:\n', AllSources()),
        TextWrapNameList('build targets:\n', AllBuilds()),
        TextWrapNameList('test targets:\n', ALL_TESTS),
    ])

    parser = argparse.ArgumentParser(
        description='Wasm waterfall top-level CI script',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog)

    parser.add_argument(
        '--sync-dir', dest='sync_dir', help='Directory for syncing sources')
    parser.add_argument(
        '--build-dir', dest='build_dir', help='Directory for build output')
    parser.add_argument(
        '--prebuilt-dir', dest='prebuilt_dir',
        help='Directory for prebuilt output')
    parser.add_argument(
        '--v8-dir', dest='v8_dir',
        help='Directory for V8 checkout/build')
    parser.add_argument(
        '--test-dir', dest='test_dir', help='Directory for test output')
    parser.add_argument(
        '--install-dir', dest='install_dir',
        help='Directory for installed output')

    sync_grp = parser.add_mutually_exclusive_group()
    sync_grp.add_argument(
        '--no-sync', dest='sync', default=True, action='store_false',
        help='Skip fetching and checking out source repos')
    sync_grp.add_argument(
        '--sync-include', dest='sync_include', default='', type=SplitComma,
        help='Include only the comma-separated list of sync targets')
    sync_grp.add_argument(
        '--sync-exclude', dest='sync_exclude', default='', type=SplitComma,
        help='Exclude the comma-separated list of sync targets')

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
        help='Exclude the comma-separated list of build targets')

    test_grp = parser.add_mutually_exclusive_group()
    test_grp.add_argument(
        '--no-test', dest='test', default=True, action='store_false',
        help='Skip running tests')
    test_grp.add_argument(
        '--test-include', dest='test_include', default='', type=SplitComma,
        help='Include only the comma-separated list of test targets')
    test_grp.add_argument(
        '--test-exclude', dest='test_exclude', default='', type=SplitComma,
        help='Exclude the comma-separated list of test targets')
    parser.add_argument(
        '--test-params', dest='test_params', default='', type=SplitComma,
        help='Test selector to pass through to emscripten testsuite runner')

    parser.add_argument(
        '--no-threads', action='store_true',
        help='Disable use of thread pool to building and testing')
    parser.add_argument(
        '--torture-filter',
        help='Limit which torture tests are run by applying the given glob')
    parser.add_argument(
        '--git-status', dest='git_status', default=False, action='store_true',
        help='Show git status for each sync target. '
             "Doesn't sync, build, or test")
    parser.add_argument(
        '--no-host-clang', dest='host_clang', action='store_false',
        help="Don't force chrome clang as the host compiler")
    parser.add_argument(
        '--no-sysroot', dest='use_sysroot', action='store_false',
        help="Don't use the V8 sysroot to build on Linux")
    parser.add_argument(
        '--clobber', dest='clobber', default=False, action='store_true',
        help="Delete working directories, forcing a clean build")

    return parser.parse_args()


def AddToPath(path):
    print("adding to path: %s" % path)
    os.environ['PATH'] = path + os.pathsep + os.environ['PATH']


def run(sync_filter, build_filter, test_filter):
    if options.git_status:
        for s in AllSources():
            s.PrintGitStatus()
        return 0

    Clobber()
    Chdir(SCRIPT_DIR)
    for work_dir in work_dirs.GetAll():
        Mkdir(work_dir)
    SyncRepos(sync_filter, options.sync_lkgr)
    if build_filter.All():
        Remove(GetInstallDir())
        Mkdir(GetInstallDir())
        Mkdir(GetInstallDir('bin'))
        Mkdir(GetInstallDir('lib'))

    # Add prebuilt cmake to PATH so any subprocesses use a consistent cmake.
    AddToPath(os.path.dirname(PrebuiltCMakeBin()))

    # `npm` uses whatever `node` is in `PATH`. To make sure it uses the
    # Node.js version we want, we prepend the node bin dir to `PATH`.
    AddToPath(NodeBinDir())

    # TODO(dschuff): Figure out how to make these statically linked?
    if IsWindows() and build_filter.Any():
        host_toolchains.CopyDlls(GetInstallDir('bin'), 'Debug')

    try:
        BuildRepos(build_filter)
    except Exception:
        # If any exception reaches here, do not attempt to run the tests; just
        # log the error for buildbot and exit
        print("Exception thrown in build step.")
        traceback.print_exc()
        buildbot.Fail()
        Summary()
        return 1

    # Override the default locale to use UTF-8 encoding for all files and stdio
    # streams (see PEP540), since oure test files are encoded with UTF-8.
    os.environ['PYTHONUTF8'] = '1'
    for t in test_filter.Apply(ALL_TESTS):
        t.Test()

    # Keep the summary step last: it'll be marked as red if the return code is
    # non-zero. Individual steps are marked as red with buildbot.Fail().
    Summary()
    return buildbot.Failed()


def main():
    global options
    start = time.time()
    options = ParseArgs()
    print('Python version %s' % sys.version)

    if options.no_threads:
        testing.single_threaded = True
    if options.torture_filter:
        compile_torture_tests.test_filter = options.torture_filter

    if options.sync_dir:
        work_dirs.SetSync(options.sync_dir)
    if options.build_dir:
        work_dirs.SetBuild(options.build_dir)
    if options.v8_dir:
        work_dirs.SetV8(options.v8_dir)
    if options.test_dir:
        work_dirs.SetTest(options.test_dir)
    if options.install_dir:
        work_dirs.SetInstall(options.install_dir)
    if options.prebuilt_dir:
        work_dirs.SetPrebuilt(options.prebuilt_dir)
    if not options.host_clang:
        host_toolchains.SetForceHostClang(False)
    if not options.use_sysroot:
        host_toolchains.SetUseSysroot(False)

    sync_include = options.sync_include if options.sync else []
    sync_filter = Filter('sync', sync_include, options.sync_exclude)
    build_include = [] if not options.build else (
        options.build_include if options.build_include else DEFAULT_BUILDS)
    build_filter = Filter('build', build_include, options.build_exclude)
    test_include = [] if not options.test else (
        options.test_include if options.test_include else DEFAULT_TESTS)
    test_filter = Filter('test', test_include, options.test_exclude)

    try:
        ret = run(sync_filter, build_filter, test_filter)
        print('Completed in {}s'.format(time.time() - start))
        return ret
    except:  # noqa
        traceback.print_exc()
        # If an except is raised during one of the steps we still need to
        # print the @@@STEP_FAILURE@@@ annotation otherwise the annotator
        # makes the failed stap as green:
        # TODO(sbc): Remove this if the annotator is fixed:
        # http://crbug.com/647357
        if buildbot.current_step:
            buildbot.Fail()
        return 1


if __name__ == '__main__':
    sys.exit(main())
