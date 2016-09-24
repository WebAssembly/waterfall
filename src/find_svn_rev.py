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

import re
import subprocess
import sys


COMMIT_MATCH = re.compile('commit ([0-9a-f]+)')
REV_MATCH = re.compile('git[-]svn[-]id[:].*[@]([0-9]+)')


def GetSvnRevFromGitCommit(commit):
  output = subprocess.check_output(['git', 'log', commit, '-n', '1'])
  m = REV_MATCH.search(output)
  if m:
    print m.group(1)
    return 0
  else:
    sys.stderr.write('Commit not found!\n')
    return 1


def GetGitCommitFromSvnRev(rev):
  output = subprocess.check_output(
      ['git', 'log', 'HEAD', '--grep', 'git-svn-id:.*[@]' + rev + '[ ]',
       '-n', '1'])
  m = COMMIT_MATCH.search(output)
  if m:
    print m.group(1)
    return 0
  else:
    sys.stderr.write('Rev not found!\n')
    return 1


def main():
  if len(sys.argv) != 2:
    sys.stderr.write('Usage: find_svn_rev.py <r#/commit>')
    return 1

  commit = sys.argv[1]
  if commit.startswith('r'):
    return GetGitCommitFromSvnRev(commit[1:])
  else:
    return GetSvnRevFromGitCommit(commit)


if __name__ == '__main__':
  sys.exit(main())
