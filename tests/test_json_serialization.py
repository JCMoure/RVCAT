import json
import unittest

import numpy as np

from RVCAT.cache import Cache
from RVCAT.exec_graph import serialize_execution_graph
from RVCAT.scheduler import Scheduler


def load_process():
    return {
        "Nloop": 10,
        "ROBsize": 4,
        "dispatch": 1,
        "retire": 1,
        "sched": "greedy",
        "nBlocks": 0,
        "blkSize": 16,
        "mPenalty": 1,
        "mIssueTime": 1,
        "instruction_list": [
            {
                "type": "MEM",
                "oper": "LOAD",
                "size": "word",
                "destin": "v",
                "source2": "A",
                "latency": 1,
                "ports": 1,
            },
            {
                "type": "MEM",
                "oper": "LOAD",
                "size": "word",
                "destin": "w",
                "source2": "B",
                "latency": 1,
                "ports": 1,
            },
        ],
    }


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

    def test_timeline_nret_limits_retirements_without_changing_memory_addresses(self):
        timeline = json.loads(Scheduler().get_timeline(load_process(), nret=3))

        self.assertEqual(len(timeline["instructions"]), 3)
        self.assertEqual(timeline["critical_path_graph"]["dynamic_instruction_count"], 3)
        self.assertEqual(
            [row[:2] for row in timeline["instructions"]],
            [[0, 0], [0, 1], [1, 0]],
        )
        self.assertEqual(
            [row[6] for row in timeline["instructions"]],
            [0, 40, 4],
        )

    def test_timeline_can_simulate_exactly_100_dynamic_instructions(self):
        timeline = json.loads(Scheduler().get_timeline(load_process(), nret=100))

        self.assertEqual(len(timeline["instructions"]), 100)
        self.assertEqual(timeline["critical_path_graph"]["dynamic_instruction_count"], 100)
        self.assertEqual(timeline["instructions"][-1][:2], [49, 1])

    def test_timeline_keeps_legacy_iteration_count_argument(self):
        process = {
            "Nloop": 10,
            "ROBsize": 4,
            "dispatch": 1,
            "retire": 1,
            "sched": "greedy",
            "nBlocks": 0,
            "blkSize": 16,
            "mPenalty": 1,
            "mIssueTime": 1,
            "instruction_list": [
                {
                    "type": "INT",
                    "oper": "ARITH",
                    "destin": "v",
                    "latency": 1,
                    "ports": 1,
                },
            ],
        }

        timeline = json.loads(Scheduler().get_timeline(process, 2))

        self.assertEqual(len(timeline["instructions"]), 2)
        self.assertEqual(timeline["critical_path_graph"]["dynamic_instruction_count"], 2)

    def test_timeline_rejects_non_positive_retirement_limit(self):
        with self.assertRaisesRegex(ValueError, "nret must be a positive integer"):
            Scheduler().get_timeline({"instruction_list": []}, nret=0)


if __name__ == "__main__":
    unittest.main()
