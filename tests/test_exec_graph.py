import random
import sys
import unittest

from RVCAT.exec_graph import (
    CompactExecutionGraph,
    exec_graph_update,
    generate_execution_graph,
    longest_path,
    find_repeating_critical_path_pattern,
)


def legacy_longest_path(graph):
    node_count = len(graph)
    dist = [-10**9 for _ in range(node_count)]
    paths = [[] for _ in range(node_count)]

    dist[node_count - 1] = 0
    paths[node_count - 1] = [[node_count - 1, 1]]
    for node in range(node_count - 1, 0, -1):
        for dependency in graph[node]:
            if dist[dependency[0]] < dist[node] + dependency[1]:
                dist[dependency[0]] = dist[node] + dependency[1]
                paths[dependency[0]] = paths[node] + [dependency]

    return paths[0]


def legacy_generate_execution_graph(static_instructions, count, window_size, dep_edges):
    graph = []
    for dynamic_idx in range(count):
        dispatch = [[(dynamic_idx - 1) * 3, 0]]
        if dynamic_idx >= window_size:
            dispatch.append([(dynamic_idx - window_size) * 3 + 2, 0])
        graph.append(dispatch)

        execute = [[dynamic_idx * 3, 1]]
        for offset in dep_edges[dynamic_idx % static_instructions]:
            dependency = dynamic_idx - offset
            if dependency >= 0:
                execute.append([dependency * 3 + 1, 0])
        graph.append(execute)

        retire = [[dynamic_idx * 3 + 1, 1], [(dynamic_idx - 1) * 3 + 2, 0]]
        graph.append(retire)
    return graph


def legacy_exec_graph_update(graph, dynamic_idx, dispatch_latency, exec_latency, retire_latency):
    dispatch_latency = min(dispatch_latency, 1)
    retire_latency = min(retire_latency, 1)
    graph[dynamic_idx * 3][0][1] = dispatch_latency

    for dependency in graph[dynamic_idx * 3 + 1][1:]:
        dependency[1] = graph[dependency[0] + 1][0][1] - 1

    graph[dynamic_idx * 3 + 2][0][1] += exec_latency
    graph[dynamic_idx * 3 + 2][1][1] = retire_latency

    if dynamic_idx == 0:
        graph[0].pop(-1)
        graph[2].pop(-1)


class LongestPathTests(unittest.TestCase):

    def test_predecessor_reconstruction_matches_previous_path_selection(self):
        randomizer = random.Random(42)
        for node_count in range(2, 30):
            graph = [[]]
            for node in range(1, node_count):
                dependencies = [[node - 1, randomizer.randint(0, 5)]]
                for dependency in range(node - 1):
                    if randomizer.random() < 0.15:
                        dependencies.append([dependency, randomizer.randint(0, 5)])
                graph.append(dependencies)

            self.assertEqual(longest_path(graph), legacy_longest_path(graph))

    def test_reconstructs_long_path_without_copying_every_prefix(self):
        node_count = 30_000
        graph = [[]] + [[[node - 1, 1]] for node in range(1, node_count)]

        path = longest_path(graph)

        self.assertEqual(len(path), node_count)
        self.assertEqual(path[0], [node_count - 1, 1])
        self.assertEqual(path[-1], [0, 1])

    def test_compact_graph_matches_original_edges_updates_and_path(self):
        static_instructions = 3
        dynamic_instructions = 18
        window_size = 5
        dependencies = [[1, 3], [1], []]
        compact = generate_execution_graph(
            static_instructions, dynamic_instructions, window_size, dependencies
        )
        original = legacy_generate_execution_graph(
            static_instructions, dynamic_instructions, window_size, dependencies
        )

        self.assertIsInstance(compact, CompactExecutionGraph)
        for dynamic_idx in range(dynamic_instructions):
            update = (dynamic_idx % 4, dynamic_idx % 6, dynamic_idx % 3)
            exec_graph_update(compact, dynamic_idx, *update)
            legacy_exec_graph_update(original, dynamic_idx, *update)
            self.assertEqual(compact.to_list(), original)

        self.assertEqual(longest_path(compact), legacy_longest_path(original))

    def test_compact_graph_uses_packed_storage(self):
        graph = generate_execution_graph(3, 1000, 32, [[1, 3], [1], []])
        original = legacy_generate_execution_graph(3, 1000, 32, [[1, 3], [1], []])

        packed_bytes = (
            graph.offsets.buffer_info()[1] * graph.offsets.itemsize
            + graph.dependencies.buffer_info()[1] * graph.dependencies.itemsize
            + graph.weights.buffer_info()[1] * graph.weights.itemsize
        )
        original_bytes = sys.getsizeof(original)
        for node in original:
            original_bytes += sys.getsizeof(node)
            for edge in node:
                original_bytes += sys.getsizeof(edge)
                original_bytes += sum(sys.getsizeof(value) for value in edge)
        self.assertLess(packed_bytes, original_bytes)

    def test_detects_longest_exact_consecutive_iteration_pattern(self):
        instruction_text = ["dispatch", "load", "sum", "store"]
        class Instruction:
            def __init__(self, text):
                self.text = text

        instructions = [Instruction(text) for text in instruction_text]
        chronological_path = [
            [0, 1],
            [16, 2], [22, 2],
            [28, 2], [34, 2],
            [40, 2], [46, 2],
            [56, 1],
        ]

        pattern = find_repeating_critical_path_pattern(
            4, instructions, list(reversed(chronological_path)), 5
        )

        self.assertEqual(pattern["start_iteration"], 2)
        self.assertEqual(pattern["end_iteration"], 4)
        self.assertEqual(pattern["repetitions"], 3)
        self.assertEqual(pattern["cycles_per_iteration"], 4)
        self.assertEqual(pattern["prefix_iterations"], 1)
        self.assertEqual(pattern["suffix_iterations"], 1)
        self.assertEqual(
            [(node["instruction_index"], node["stage"], node["cycles"]) for node in pattern["nodes"]],
            [(1, "execute", 2), (3, "execute", 2)],
        )

    def test_does_not_report_a_single_iteration_signature(self):
        class Instruction:
            text = "instruction"

        path = [[3 * dynamic_idx + 1, 2] for dynamic_idx in reversed(range(3))]
        self.assertIsNone(
            find_repeating_critical_path_pattern(3, [Instruction()], path, 3)
        )


if __name__ == "__main__":
    unittest.main()
