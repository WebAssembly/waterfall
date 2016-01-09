# Waterfall

## ༼ ༎ຶ ෴ ༎ຶ༽ If it’s not tested, it’s already broken.

Luckily, this repository has some tests: [![Build Status](https://travis-ci.org/WebAssembly/waterfall.svg?branch=master)](https://travis-ci.org/WebAssembly/waterfall)

# What's this?

This repository holds the code which make the WebAssembly waterfall's heart
beat. You may want to see [the waterfall][] in action, and if you don't like
what you see you may even want to [contribute](Contributing.md).

  [the waterfall]: https://build.chromium.org/p/client.wasm.llvm/console

# What's a waterfall?

WebAssembly has many moving parts and no central owner. Some of these interact
closely, some implement the same thing. A build and test waterfall allows us to:

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

# Details

The code is in the process of moving from its [old hosting location][]. We need
to set up mirrors and provision robots to do our bidding. The documentation and
design will be improved as this goes on.

And yes, the URL of the waterfall will change. It's more complicated than it
seems.

  [old hosting location]: https://github.com/WebAssembly/experimental/tree/master/buildbot
