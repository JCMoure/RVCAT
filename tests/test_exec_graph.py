import random
import unittest

from RVCAT.exec_graph import longest_path


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


if __name__ == "__main__":
    unittest.main()
