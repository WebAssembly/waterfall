import multiprocessing
import Queue
import sys


def g_testing_thread(test_function, work_queue, result_queue):
  for test in iter(lambda: get_from_queue(work_queue), None):
    result = None
    try:
      result = test_function(test)
    except Exception as e:
      print >> sys.stderr, "Something went wrong", e
      raise
    result_queue.put(result)


class ParallelRunner(object):
  def __init__(self):
    self.processes = None
    self.result_queue = None

  def run(self, test_function, inputs):
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
    #self.dedicated_temp_dirs = [tempfile.mkdtemp() for x in range(num_cores())]
    for x in range(16 or multiprocessing.cpu_count()):
      p = multiprocessing.Process(target=g_testing_thread,
                                  args=(test_function, test_queue, self.result_queue))
      p.start()
      self.processes.append(p)

  def collect_results(self):
    buffered_results = []
    while len(self.processes):
      res = get_from_queue(self.result_queue)
      if res is not None:
        buffered_results.append(res)
      else:
        self.clear_finished_processes()
    return buffered_results

  def clear_finished_processes(self):
    self.processes = [p for p in self.processes if p.is_alive()]

  def combine_results(self, result, buffered_results):
    print()
    print('DONE: combining results on main thread')
    print()
    # Sort the results back into alphabetical order. Running the tests in
    # parallel causes mis-orderings, this makes the results more readable.
    results = sorted(buffered_results, key=lambda res: str(res.test))
    for r in results:
      r.updateResult(result)
    return result

def get_from_queue(q):
  try:
    return q.get(True, 0.1)
  except Queue.Empty:
    pass
  return None
