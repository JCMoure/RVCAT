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

    def test_cache_records_reserved_main_memory_request_cycles(self):
        cache = Cache(1, 16, MissLatency=10, MissIssueTime=4, record_requests=True)
        cache.access(1, 0, 1, 3)
        cache.access(1, 16, 2, 4)

        self.assertEqual(cache.MEM_requests, [
            {"cycle": 1, "address": 0, "operation": "read_for_write", "instruction_index": 3, "duration": 4},
            {"cycle": 5, "address": 16, "operation": "read_for_write", "instruction_index": 4, "duration": 4},
            {"cycle": 9, "address": 0, "operation": "write", "instruction_index": 4, "duration": 4},
        ])

    def test_cache_state_reports_block_address_dirty_bit_and_pending_fill(self):
        cache = Cache(2, 8, MissLatency=4, MissIssueTime=2)

        self.assertFalse(cache.get_state(0)[0]["valid"])
        cache.access(1, 8, 0)

        loading_line = cache.get_state(0)[0]
        self.assertEqual(loading_line["address"], 8)
        self.assertTrue(loading_line["dirty"])
        self.assertIsInstance(loading_line["lru"], int)
        self.assertTrue(loading_line["loading"])
        self.assertEqual(loading_line["ready_cycle"], 4)
        self.assertFalse(cache.get_state(4)[0]["loading"])

    def test_read_hit_preserves_dirty_bit_for_a_later_writeback(self):
        cache = Cache(1, 8, MissLatency=4, MissIssueTime=2, record_requests=True)
        cache.access(1, 8, 0)

        result, _ = cache.access(0, 8, 4)

        self.assertEqual(result, 0)
        self.assertTrue(cache.get_state(4)[0]["dirty"])
        cache.access(0, 16, 5)
        self.assertTrue(any(
            request["operation"] == "write" and request["address"] == 8
            for request in cache.MEM_requests
        ))

    def test_cache_does_not_record_requests_outside_timeline_generation(self):
        cache = Cache(1, 16, MissLatency=10, MissIssueTime=4)
        cache.access(0, 0, 1)

        self.assertEqual(cache.MEM_requests, [])

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

    def test_timeline_serializes_per_cycle_port_and_main_memory_usage(self):
        process = load_process()
        process.update({
            "nBlocks": 1,
            "blkSize": 4,
            "mPenalty": 4,
            "mIssueTime": 2,
        })

        timeline = json.loads(Scheduler().get_timeline(process, nret=4))
        resource_usage = timeline["resource_usage"]

        self.assertEqual(set(resource_usage["ports"]), {"0"})
        self.assertEqual(len(resource_usage["ports"]["0"]), timeline["cycles"])
        self.assertTrue(any(resource_usage["ports"]["0"]))
        self.assertEqual(len(resource_usage["mm"]), timeline["cycles"])
        self.assertTrue(any(resource_usage["mm"]))
        self.assertTrue(resource_usage["mm_requests"])
        cache_state = resource_usage["cache_state"]
        self.assertEqual(cache_state["line_count"], 1)
        self.assertTrue(cache_state["snapshots"])
        self.assertEqual(
            [snapshot["cycle"] for snapshot in cache_state["snapshots"]],
            sorted(snapshot["cycle"] for snapshot in cache_state["snapshots"]),
        )
        self.assertTrue(all(
            len(snapshot["lines"]) == cache_state["line_count"]
            for snapshot in cache_state["snapshots"]
        ))
        self.assertIn(
            40,
            [line["address"] for snapshot in cache_state["snapshots"]
             for line in snapshot["lines"] if line["valid"]],
        )
        self.assertTrue(all(
            isinstance(request["address"], int)
            and request["operation"] in {"read", "read_for_write", "write"}
            and isinstance(request["instruction_index"], int)
            and request["instruction_index"] < len(timeline["instructions"])
            for request in resource_usage["mm_requests"]
        ))
        self.assertTrue(all(
            timeline["instructions"][request["instruction_index"]][6] == request["address"]
            for request in resource_usage["mm_requests"]
        ))
        for row in timeline["instructions"]:
            issue_offset = next(
                (index for index, state in enumerate(row[4]) if state in "ELS"),
                None,
            )
            self.assertIsNotNone(issue_offset)
            issue_cycle = row[2] + issue_offset
            self.assertTrue(resource_usage["ports"][str(row[3])][issue_cycle])

    def test_store_miss_reads_requested_block_and_writes_back_dirty_block(self):
        process = load_process()
        process.update({
            "nBlocks": 1,
            "blkSize": 4,
            "mPenalty": 4,
            "mIssueTime": 2,
        })
        for instruction in process["instruction_list"]:
            instruction["oper"] = "STORE"

        timeline = json.loads(Scheduler().get_timeline(process, nret=4))
        requests = timeline["resource_usage"]["mm_requests"]
        cache_lines = [
            line
            for snapshot in timeline["resource_usage"]["cache_state"]["snapshots"]
            for line in snapshot["lines"]
            if line["valid"]
        ]

        self.assertIn(
            {"cycle": 2, "address": 0, "operation": "read_for_write",
             "instruction_index": 0, "duration": 2},
            requests,
        )
        self.assertTrue(any(
            request["operation"] == "read_for_write" and request["address"] == 40
            for request in requests
        ))
        self.assertTrue(any(
            request["operation"] == "write" and request["address"] == 0
            for request in requests
        ))
        self.assertTrue(any(line["dirty"] for line in cache_lines))

    def test_timeline_omits_main_memory_usage_without_cache(self):
        timeline = json.loads(Scheduler().get_timeline(load_process(), nret=2))

        self.assertNotIn("mm", timeline["resource_usage"])

    def test_timeline_reports_blocking_data_dependency_by_cycle(self):
        process = load_process()
        process["instruction_list"][1]["source1"] = "v"
        process["instruction_list"][0]["latency"] = 4

        timeline = json.loads(Scheduler().get_timeline(process, nret=4))
        wait_details = timeline["wait_details"]
        data_waits = [detail for detail in wait_details if detail["reason"] == "data"]

        self.assertTrue(data_waits)
        self.assertTrue(all(detail["dependencies"] for detail in data_waits))
        for detail in data_waits:
            row = timeline["instructions"][detail["instruction_index"]]
            self.assertEqual(row[4][detail["cycle"] - row[2]], ".")

    def test_timeline_reports_ports_blocking_issue(self):
        process = load_process()
        process.update({"dispatch": 2, "sched": "greedy"})
        process["instruction_list"][0]["ports"] = 3

        timeline = json.loads(Scheduler().get_timeline(process, nret=4))
        port_waits = [detail for detail in timeline["wait_details"] if detail["reason"] == "ports"]

        self.assertTrue(port_waits)
        self.assertTrue(all(detail["ports"] == [0] for detail in port_waits))
        for detail in port_waits:
            row = timeline["instructions"][detail["instruction_index"]]
            self.assertEqual(row[4][detail["cycle"] - row[2]], "*")

    def test_timeline_reports_all_blocking_data_dependencies(self):
        process = load_process()
        process["instruction_list"][0]["latency"] = 4
        process["instruction_list"][1]["source1"] = "v"
        process["instruction_list"].append({
            "type": "FLOAT",
            "oper": "ADD",
            "size": "single",
            "destin": "z",
            "source1": "v",
            "source2": "w",
            "latency": 1,
            "ports": 1,
        })

        timeline = json.loads(Scheduler().get_timeline(process, nret=6))
        data_waits = [detail for detail in timeline["wait_details"] if detail["reason"] == "data"]

        self.assertTrue(data_waits)
        multi_dependency_waits = [
            detail for detail in data_waits if len(detail["dependencies"]) > 1
        ]
        self.assertTrue(multi_dependency_waits)
        self.assertIn([0, 1], [detail["dependencies"] for detail in multi_dependency_waits])
        for detail in data_waits:
            row = timeline["instructions"][detail["instruction_index"]]
            self.assertEqual(row[4][detail["cycle"] - row[2]], ".")

    def test_timeline_distinguishes_issue_bandwidth_waits_from_port_conflicts(self):
        process = load_process()
        process.update({"dispatch": 2, "sched": "greedy"})

        timeline = json.loads(Scheduler().get_timeline(process, nret=4))
        bandwidth_waits = [
            detail for detail in timeline["wait_details"]
            if detail["reason"] == "issue-bandwidth"
        ]

        self.assertTrue(bandwidth_waits)
        for detail in bandwidth_waits:
            row = timeline["instructions"][detail["instruction_index"]]
            self.assertEqual(row[4][detail["cycle"] - row[2]], "^")

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
