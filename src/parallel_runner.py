#! /usr/bin/env python

#   Copyright 2018 WebAssembly Community Group participants
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

from __future__ import print_function
import multiprocessing
import sys
if sys.version_info.major == 2:
  import Queue as queue
else:
  import queue


def g_testing_thread(test_function, work_queue, result_queue):
  for test in iter(lambda: get_from_queue(work_queue), None):
    result = None
    try:
      result = test_function(test)
    except Exception as e:
      print("Something went wrong", e, file=sys.stderr)
      raise
    result_queue.put(result)


class ParallelRunner(object):
  def __init__(self):
    self.processes = None
    self.result_queue = None

  def map(self, test_function, inputs):
    test_queue = self.create_test_queue(inputs)
    self.init_processes(test_function, test_queue)
    results = self.collect_results()
    return results

  def create_test_queue(self, inputs):
    test_queue = multiprocessing.Queue()
    for test in inputs:
      test_queue.put(test)
    return test_queue

  def init_processes(self, test_function, test_queue):
    self.processes = []
    self.result_queue = multiprocessing.Queue()
    for x in range(multiprocessing.cpu_count()):
      p = multiprocessing.Process(
          target=g_testing_thread,
          args=(test_function, test_queue, self.result_queue))
      p.start()
      self.processes.append(p)

  def collect_results(self):
    buffered_results = []
    num = 0
    while len(self.processes):
      res = get_from_queue(self.result_queue)
      if res is not None:
        num += 1
        # Print periodically to assure the bot monitor that we are still alive
        if num % 10 == 0:
          print('Got test results:', num)
        buffered_results.append(res)
      else:
        self.clear_finished_processes()
    return buffered_results

  def clear_finished_processes(self):
    self.processes = [p for p in self.processes if p.is_alive()]


def get_from_queue(q):
  try:
    return q.get(True, 0.1)
  except queue.Empty:
    pass
  return None
