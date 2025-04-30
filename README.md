# rvcat
RISC-V Code Analysis Tool


## Overview
This is a RISC-V assembly code execution simulation tool for the performance
analysis of small programs from a computer architecture educational standpoint.

One of the major similar projects is the `llvm-mca` tool, from the LLVM project.


## Commands
One of the main ways to use the tool will be an interactive shell. This shell
will proportionate a custom set of commands.

Note: Commands marked with * are not yet implemented and can be considered
proposals, even though all of them can be susceptible to change.

### `load`
* `load program <file>` loads the `file` containing the assembly code

* `load processor <file>` loads the processor configuration `file`

* `load isa <file>` loads an isa csv `file` with instructions to the working ISA

### `show`
* `show program [-a, --annotate | -d, --dependencies]` shows the loaded
  program's instructions (no flag), and optionally, it's annotated (`-a,
  --annotate`) or dependency (`-d, --dependencies`) form

* `show processor` shows the processor's attributes

* `show isa` shows the current working ISA instructions

### `info`
* `info <mnemonic>` informs about a certain instruction given its `mnemonic`

### `run`
* `run [-i, --iterations n] [-w, --window_size s] timeline` runs the program and
  shows a timeline view of the execution, optionally specifying the number of
  iterations `n` (`-i, --iterations`) and execution window size (`-w,
  --window_size`).

* `run [-i, --iterations n] [-w, --window_size s] analysis` runs the program and
  analyzes the execution, showing performance counters and stats, optionally
  specifying the number of iterations `n` (`-i, --iterations`) and execution
  window size `s` (`-w, --window_size`) in number of instructions.

### `set`
* `set processor <attribute> <value>`* sets a specific processor's `attribute`
  to a certain `value`


## Arguments
Although it's supposed that the main way to execute actions will be via the
interactive shell, the tool will also proportionate equivalent arguments to the
former's commands.


## Requirements
* Python 3.8 or higher
* `cmd2` package (`pip install cmd2`)


## Installation and sample usage
```
git clone https://github.com/smarco/rvcat.git
cd rvcat
./rvcat                       # gives shell
load program vectoradd        # load program
show program                  # show instructions
show program -a               # show annotated program
show program -d               # show execution properties
run -i 4 -w 30 timeline       # run in timeline mode for 4 iterations with a 30 instruction window
run -i 1000 -w 100 analysis   # run in analysis mode for 1000 iterations with a 100 instruction window
```

Alternatively, one can also save commands to a file (e.g. a `script` file),
 for later input redirection without going on interactive mode:
```
./rvcat examples/arraysum.s < script
```

## Authors
Saúl Adserias Valero

Juan Carlos Moure

Santiago Marco-Sola
