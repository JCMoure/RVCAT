import json
import unittest

import numpy as np

from RVCAT.cache import Cache
from RVCAT.exec_graph import serialize_execution_graph


class JsonSerializationTests(unittest.TestCase):

    def test_secondary_cache_miss_latency_is_json_serializable(self):
        cache = Cache(1, 16, MissLatency=10, MissIssueTime=4)
        cache.access(0, 0, 0)

        result, latency = cache.access(0, 0, 1)

        self.assertEqual(result, 2)
        self.assertIs(type(latency), int)
        self.assertEqual(json.dumps({"latency": latency}), '{"latency": 10}')

    def test_execution_graph_converts_numpy_integer_values(self):
        graph = [[(np.int64(0), np.int64(1))], []]

        serialized = serialize_execution_graph(graph, np.int64(1))

        self.assertEqual(
            json.dumps(serialized),
            '{"version": 1, "dynamic_instruction_count": 1, "node_count": 2, '
            '"source": 0, "sink": 1, "stages": ["dispatch", "execute", "retire"], '
            '"dependencies_by_node": [[[0, 1]], []]}'
        )


if __name__ == "__main__":
    unittest.main()
