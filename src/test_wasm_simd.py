#!/usr/bin/env python

"""
Tests that SIMD operations are compiled to intrinsic instructions.
For each operation and vector type listed in the test cases, a
simple test program is generated and compiled, and the compiled
output is verified to consist of a single SIMD instruction.
"""

from __future__ import print_function
import os
import re
import subprocess
import sys
import tempfile

wasm_simd_test_cases = [
  # Oper Arity ArgType     ReturnType   Opcode   KnownFailure
  ('add',  2, 'int32x4',   'int32x4',   'add',   False),
  ('add',  2, 'int16x8',   'int16x8',   'add',   False),
  ('add',  2, 'int8x16',   'int8x16',   'add',   False),
  ('sub',  2, 'int32x4',   'int32x4',   'sub',   False),
  ('sub',  2, 'int16x8',   'int16x8',   'sub',   False),
  ('sub',  2, 'int8x16',   'int8x16',   'sub',   False),
  ('mul',  2, 'int32x4',   'int32x4',   'mul',   False),
  ('mul',  2, 'int16x8',   'int16x8',   'mul',   False),
  ('mul',  2, 'int8x16',   'int8x16',   'mul',   False),
  ('add',  2, 'float64x2', 'float64x2', 'fadd',  False),
  ('add',  2, 'float32x4', 'float32x4', 'fadd',  False),
  ('sub',  2, 'float64x2', 'float64x2', 'fsub',  False),
  ('sub',  2, 'float32x4', 'float32x4', 'fsub',  False),
  ('mul',  2, 'float64x2', 'float64x2', 'fmul',  False),
  ('mul',  2, 'float32x4', 'float32x4', 'fmul',  False),
  ('div',  2, 'float64x2', 'float64x2', 'fdiv',  False),
  ('div',  2, 'float32x4', 'float32x4', 'fdiv',  False),
  ('min',  2, 'float64x2', 'float64x2', 'fmin',  True ),
  ('min',  2, 'float32x4', 'float32x4', 'fmin',  True ),
  ('max',  2, 'float64x2', 'float64x2', 'fmax',  True ),
  ('max',  2, 'float32x4', 'float32x4', 'fmax',  True ),
  ('abs',  1, 'float64x2', 'float64x2', 'fabs',  True ),
  ('abs',  1, 'float32x4', 'float32x4', 'fabs',  True ),
  ('neg',  1, 'float64x2', 'float64x2', 'fsub',  False),
  ('neg',  1, 'float32x4', 'float32x4', 'fsub',  False),
  ('sqrt', 1, 'float64x2', 'float64x2', 'fsqrt', True ),
  ('sqrt', 1, 'float32x4', 'float32x4', 'fsqrt', True ),
]

def create_test_file(datatype, operation, arity, returntype):
  f = tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False)
  f.write('#include <emscripten/vector.h>\n\n')
  if arity == 2:
    f.write('%s test(%s a, %s b) {\n' % (returntype, datatype, datatype))
    f.write('  return emscripten_%s_%s(a, b);\n' % (datatype, operation))
    f.write('}\n')
  else:
    f.write('%s test(%s a) {\n' % (returntype, datatype))
    f.write('  return emscripten_%s_%s(a);\n' % (datatype, operation))
    f.write('}\n')
  f.close()
  return f.name

def compile_test_file(filename, clang, include):
  p = subprocess.Popen([clang, '-w', '-S', '-emit-llvm', filename,
                        '-O3', '-o-', '-I', include],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  stdout, stderr = p.communicate()
  if p.returncode != 0:
    print('================================================================')
    print(stderr.strip())
    print('================================================================')
    return False, 'Compiler error (see above)'
  else:
    return True, stdout

def check_test_output(output, opcode, arity):
  param_pattern = r', '.join(r'<.+> %\w' for x in range(arity))
  operand_pattern = r', '.join(r'%\w' for x in range(arity))
  pattern = (
    r'define <.+> @test\(' + param_pattern + r'\) local_unnamed_addr #\d \{\s+' +
    r'entry:\s+' +
    r'(%.+) = ([A-Za-z0-9]+) .+ ' + operand_pattern + r'\s+' +
    r'ret <.+> \1\s+' +
    r'\}')
  m = re.search(pattern, output)
  if m:
    if m.group(2) == opcode:
      return True, None
    else:
      return False, 'Expected operation %s but found %s' % (opcode, m.group(2))
  else:
    print('================================================================')
    m = re.search(r'define .+ \{[^}]+\}', output)
    if m:
      print(m.group(0).strip())
      err = 'Compiled function not in intrinsic form (see above)'
    else:
      print(output.strip())
      err = 'Compiled function not found (see above)'
    print('================================================================')
    return False, err

def test_wasm_simd_instruction(datatype, operation, arity, returntype, opcode, clang, include):
  filename = create_test_file(datatype, operation, arity, returntype)
  passed, output = compile_test_file(filename, clang, include)
  if passed:
    passed, err = check_test_output(output, opcode, arity)
    if passed:
      print('%s %s: PASSED' % (datatype, operation))
    else:
      print('%s %s: FAILED: %s' % (datatype, operation, err))
  else:
    print('%s %s: FAILED: %s' % (datatype, operation, output))
  os.remove(filename)
  return passed

def test_wasm_simd(clang, include):
  passed_expectedly = 0
  passed_unexpectedly = 0
  failed_expectedly = 0
  failed_unexpectedly = 0
  for (operation, arity, datatype, returntype, opcode, expect_failure) in wasm_simd_test_cases:
    if test_wasm_simd_instruction(datatype, operation, arity, returntype, opcode, clang, include):
      if expect_failure:
        passed_unexpectedly += 1
      else:
        passed_expectedly += 1
    elif expect_failure:
      failed_expectedly += 1
    else:
      failed_unexpectedly += 1
  print('Passes (expected):', passed_expectedly)
  print('Passes (unexpected):', passed_unexpectedly)
  print('Failures (expected):', failed_expectedly)
  print('Failures (unexpected):', failed_unexpectedly)
  return passed_unexpectedly + failed_unexpectedly

if __name__ == '__main__':
  clang = sys.argv[1] if len(sys.argv) > 1 else 'clang'
  include = sys.argv[2] if len(sys.argv) > 2 else '../system/include/'
  sys.exit(test_wasm_simd(clang, include))
