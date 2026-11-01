# rvcat
Machine Code Analysis Tool

## Overview
This is a machine code execution simulation tool for the performance analysis of small programs 
from a computer architecture educational standpoint.
One of the major similar projects is the `llvm-mca` tool, from the LLVM project.
The tool is tailored to be used as a kernel of a web-based interactive application.

## Timeline critical-path data

`Scheduler.get_timeline()` returns JSON with the existing `cycles`, `instructions`, and
`arrays` fields, plus `critical_path_graph`. The graph lets a consumer independently
compute the same longest weighted execution path from the completed simulation.

The graph has this versioned shape:

```json
{
  "version": 1,
  "dynamic_instruction_count": 1,
  "node_count": 3,
  "source": 0,
  "sink": 2,
  "stages": ["dispatch", "execute", "retire"],
  "dependencies_by_node": [
    [],
    [[0, 1]],
    [[1, 4]]
  ]
}
```

Each dynamic instruction contributes three graph nodes, in dispatch/execute/retire
order. Thus node `3*i + stage` belongs to dynamic instruction `i`, with stage indexes
0, 1, and 2 respectively. `dependencies_by_node[u]` is the list of weighted
predecessors for node `u`; each entry is `[predecessor_node_index, edge_weight]`.
These entries preserve the scheduler's measured dispatch, execution, and retirement
latencies and the data, reorder-window, and in-order constraints in the execution DAG.
The source is node 0 and the sink is the retire node of the last dynamic instruction.

Timeline `instructions` rows retain their existing seven-element layout:
`[iteration, static_instruction_index, start_cycle, port, states, critical_cycles, address]`.
Rows are ordered by dynamic instruction index, which aligns them with graph nodes.
The `critical_cycles` values remain in the response during the transition to
client-side path calculation so consumers can compare results.

Consumers should reject unsupported graph versions or inconsistent node/row counts.
Longest-path calculation is linear in graph nodes plus edges (`O(V + E)`).

## Requirements
* Python 3.8 or higher

## Authors
Saúl Adserias Valero

Juan Carlos Moure
