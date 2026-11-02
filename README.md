# rvcat
Machine Code Analysis Tool

## Overview
This is a machine code execution simulation tool for the performance analysis of small programs 
from a computer architecture educational standpoint.
One of the major similar projects is the `llvm-mca` tool, from the LLVM project.
The tool is tailored to be used as a kernel of a web-based interactive application.

## Timeline critical-path data

`Scheduler.get_timeline()` returns JSON with the existing `cycles`, `instructions`, and
`arrays` fields, plus `critical_path_graph` and per-cycle `resource_usage`. The graph
lets a consumer independently compute the same longest weighted execution path from
the completed simulation. When a cache is enabled, `resource_usage.mm_requests` lists
each Main Memory request with its starting cycle, block address, read/write operation,
originating dynamic instruction index, and reserved channel duration. Store misses
are recorded as `read_for_write` requests; dirty-block writebacks are `write` requests.
When a cache is enabled, `resource_usage.cache_state` contains transition snapshots
of each cache line at the end of a cycle, including its block address, dirty bit,
LRU rank, and pending-fill ready cycle. Snapshots are recorded only when line state
changes.
`wait_details` identifies the dynamic instruction and cycle behind port conflicts,
issue-width limits, and unresolved data dependencies. A data wait lists every
outstanding producer in its `dependencies` array.

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

`Scheduler.get_timeline(processJSON, niters=3, nret=None)` preserves the legacy
iteration-based behavior when `nret` is omitted. When supplied, `nret` sets the
exact number of dynamic instructions simulated for the timeline and takes precedence
over `niters`; it does not change `processJSON["Nloop"]`, which determines memory
addresses. A timeline may therefore end partway through a loop iteration.

The execution graph is stored internally in packed offset, dependency, and weight
arrays. This preserves edge ordering and path tie-breaking while avoiding per-edge
Python lists. Simulation results also include `critical_path.repeating_pattern`
when identical non-empty critical-path signatures occur in consecutive iterations;
the signature includes each instruction, stage, and cycle weight.

Consumers should reject unsupported graph versions or inconsistent node/row counts.
Longest-path calculation is linear in graph nodes plus edges (`O(V + E)`). It stores
distances and predecessor links, reconstructing only the selected path instead of
copying a full path for every graph node.

## Requirements
* Python 3.8 or higher

## Authors
Saúl Adserias Valero

Juan Carlos Moure
