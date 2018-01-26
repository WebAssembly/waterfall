# Waterfall

## ༼ ༎ຶ ෴ ༎ຶ༽ If it’s not tested, it’s already broken.

Luckily, this repository has some tests: [![Build Status](https://travis-ci.org/WebAssembly/waterfall.svg?branch=master)](https://travis-ci.org/WebAssembly/waterfall)

# What's this?

This repository holds the code which make the WebAssembly waterfall's heart
beat. You may want to see [the waterfall][] in action, and if you don't like
what you see you may even want to [contribute](Contributing.md).

  [the waterfall]: https://wasm-stat.us

# What's a waterfall?

WebAssembly has many moving parts (implementations, tools, tests, etc) and no central owner. All of these
parts have have their own owners, priorities, and tests (which include WebAssembly as well as others).
A build and test waterfall allows us to test the interactions between these components. It helps us:

* Have simple build instructions for each component.
* Archive build logs and build artifacts.
* Identify which build artifacts are known-good.
* Know which tests matter.
* Make tests easily executable.
* Know which configurations matter (build flavor, host OS, host architecture,
  ...).
* Cause inadvertent breakage less often.
* When breakage occurs, identify it quickly and reverted / silenced / fixed
  easily.
* When a big change is required, know which moving parts should synchronize.
* Make the feature implementation status straightforward to check for each
  component.

We should keep process to a minimum, try things out, see what works.

# How do I run it?

1. Get the sources: `$ git clone https://github.com/WebAssembly/waterfall.git`
2. Run build.py `python src/build.py`

Build.py has 3 types of actions: downloading/updating sources for tools and engines (sync), 
building those sources (build), and runnint tests against them (test). Each of these types
has multiple steps (e.g. a build step for each component).
If you run build.py with no arguments, it will run all the sync, build, and test steps. If
you make a change and only want to run a subset of steps, you can apply filters from the
command line, via exclusions (to prevent specified steps from running) or inclusions
(to run only the specified steps). Sync, build, and test exclusions are specified separately.
For example:
1. Do not sync any sources, build everything except LLVM, and run all tests: 
`$ src/build.py --no-sync --build-exclude=llvm`
2. Sync only WABT, build WABT and Binaryen, run everything other than the emscripten testsuites: 
`$ src/build.py --sync-include=wabt --build-include=wabt,binaryen --test-exclude=emtest,emtest-asm`
The script should throw an error if you specify nonexistent steps or if you specify both includes and excludes for the
same type of action.
