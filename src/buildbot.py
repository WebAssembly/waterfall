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

import os
import sys


failed_steps = []
warned_steps = []
current_step = None

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


def IsBot():
  """Return True if we are running on bot, False otherwise."""
  return BUILDBOT_BUILDNUMBER is not None


def Revision():
  return BUILDBOT_REVISION


def BuildNumber():
  return BUILDBOT_BUILDNUMBER


def ShouldClobber():
  return os.environ.get('BUILDBOT_CLOBBER')


def BuilderName():
  return BUILDBOT_BUILDERNAME


def Scheduler():
  return BUILDBOT_SCHEDULER


# Magic annotations:
# https://chromium.googlesource.com/chromium/tools/build/+/master/scripts/common/annotator.py
def Step(name):
  global current_step
  current_step = name
  sys.stdout.flush()
  sys.stdout.write('\n@@@BUILD_STEP %s@@@\n' % name)


def Link(label, url):
  sys.stdout.write('@@@STEP_LINK@%s@%s@@@\n' % (label, url))


def Fail():
  """Mark one step as failing, but keep going."""
  sys.stdout.flush()
  sys.stdout.write('\n@@@STEP_FAILURE@@@\n')
  global failed_steps
  failed_steps.append(current_step)


def Failed():
  return len(failed_steps)


def FailedList():
  return list(failed_steps)


def Warn():
  """We mark this step as failing, but this step is flaky so we don't care
  enough about this to make the bot red."""
  sys.stdout.flush()
  sys.stdout.write('\n@@@STEP_WARNINGS@@@\n')
  global warned_steps
  warned_steps.append(current_step)


def Warned():
  return len(warned_steps)


def WarnedList():
  return list(warned_steps)


def DidStepFailOrWarn(step):
  return step in failed_steps or step in warned_steps


def FailUnless(predicate):
  if predicate():
    Warn()
  else:
    Fail()
