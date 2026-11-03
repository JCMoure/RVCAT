import json
import unittest

import numpy as np

from RVCAT.cache import Cache
from RVCAT.exec_graph import serialize_execution_graph
from RVCAT.program import Process
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
        "nFillBuffers": 2,
        "nWriteBuffers": 2,
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

    def test_process_rejects_miss_penalty_below_memory_issue_time(self):
        process = load_process()
        process["mPenalty"] = 1
        process["mIssueTime"] = 2

        with self.assertRaisesRegex(
            ValueError,
            "mPenalty must be greater than or equal to mIssueTime",
        ):
            Process.from_json(process)

    def test_simulation_results_separate_read_miss_types_and_count_mm_transfers(self):
        process = load_process()
        process.update({
            "Nloop": 1,
            "nBlocks": 1,
            "blkSize": 8,
            "mPenalty": 4,
            "mIssueTime": 1,
        })
        process["instruction_list"][1]["source2"] = "A"

        results = json.loads(Scheduler().get_results(process, niters=1))

        self.assertEqual(results["read_misses"], 2)
        self.assertEqual(results["read_primary_misses"], 1)
        self.assertEqual(results["read_secondary_misses"], 1)
        self.assertEqual(results["write_misses"], 0)
        self.assertEqual(results["MM_Reads"], 1)
        self.assertEqual(results["MM_Writes"], 0)
        self.assertAlmostEqual(
            results["MM_usage_percent"],
            100 / results["total_cycles"],
        )

    def test_simulation_counts_dirty_block_writebacks_as_mm_writes(self):
        process = load_process()
        process.update({
            "Nloop": 1,
            "nBlocks": 1,
            "blkSize": 4,
            "mPenalty": 4,
            "mIssueTime": 1,
        })
        for instruction in process["instruction_list"]:
            instruction["oper"] = "STORE"

        results = json.loads(Scheduler().get_results(process, niters=1))

        self.assertEqual(results["write_misses"], 2)
        self.assertEqual(results["write_primary_misses"], 2)
        self.assertEqual(results["write_secondary_misses"], 0)
        self.assertEqual(results["MM_Reads"], 2)
        self.assertEqual(results["MM_Writes"], 1)
        self.assertAlmostEqual(
            results["MM_usage_percent"],
            300 / results["total_cycles"],
        )

    def test_simulation_splits_secondary_store_misses(self):
        process = load_process()
        process.update({
            "Nloop": 1,
            "nBlocks": 1,
            "blkSize": 8,
            "mPenalty": 4,
            "mIssueTime": 1,
        })
        process["instruction_list"][0]["oper"] = "STORE"
        process["instruction_list"][1]["oper"] = "STORE"
        process["instruction_list"][1]["source2"] = "A"

        results = json.loads(Scheduler().get_results(process, niters=1))

        self.assertEqual(results["write_misses"], 2)
        self.assertEqual(results["write_primary_misses"], 1)
        self.assertEqual(results["write_secondary_misses"], 1)
        self.assertEqual(results["MM_Reads"], 1)
        self.assertEqual(results["MM_Writes"], 0)

    def test_return_throughput_defaults_to_one_and_rejects_invalid_values(self):
        process = Process.from_json(load_process())
        self.assertEqual(process.rThru, 1)
        self.assertEqual(process.json()["rThru"], 1)

        for invalid_value in (0, 33, True, 1.5):
            with self.subTest(value=invalid_value):
                invalid_process = load_process()
                invalid_process["rThru"] = invalid_value
                with self.assertRaisesRegex(ValueError, "rThru must be an integer"):
                    Process.from_json(invalid_process)

    def test_secondary_cache_miss_latency_is_json_serializable(self):
        cache = Cache(1, 16, MissLatency=4, MissIssueTime=2, record_requests=True)
        self.assertEqual(cache.request_access(0, 0, 0, 0), "miss")
        self.assertEqual(cache.request_access(0, 0, 0, 1), "merged")
        cache.advance(0)
        self.assertEqual(len(cache.MEM_requests), 1)
        self.assertEqual(cache.MEM_requests[0]["instruction_indices"], [0, 1])
        self.assertEqual(cache.get_request_state(0), "reading")
        self.assertEqual(cache.get_request_state(1), "reading")
        cache.advance(4)

        self.assertEqual(cache.get_request_state(0), "returned")
        self.assertEqual(cache.get_request_state(1), "return_queue")
        return_fill = cache.get_buffer_state()["fill"][0]
        self.assertTrue(return_fill["valid"])
        self.assertEqual(return_fill["state"], "returning")
        self.assertEqual(return_fill["instruction_indices"], [0, 1])
        self.assertTrue(cache.consume_completion(0))
        self.assertEqual(
            cache.get_buffer_state()["fill"][0]["instruction_indices"], [1]
        )
        cache.advance(5)
        self.assertEqual(cache.get_request_state(1), "returned")
        self.assertTrue(cache.consume_completion(1))
        self.assertFalse(cache.get_buffer_state()["fill"][0]["valid"])

    def test_cache_return_throughput_serves_waiters_in_age_order(self):
        cache = Cache(
            1, 16, MissLatency=4, MissIssueTime=2,
            return_throughput=2,
        )
        cache.request_access(0, 0, 0, 3)
        cache.request_access(0, 0, 0, 1)
        cache.request_access(0, 0, 0, 2)
        cache.advance(0)
        cache.advance(4)

        self.assertEqual(cache.returned_instructions, [1, 2])
        self.assertEqual(cache.get_request_state(1), "returned")
        self.assertEqual(cache.get_request_state(2), "returned")
        self.assertEqual(cache.get_request_state(3), "return_queue")
        self.assertTrue(cache.consume_completion(1))
        self.assertTrue(cache.consume_completion(2))
        cache.advance(5)
        self.assertEqual(cache.returned_instructions, [3])

    def test_cache_records_cycle_issued_read_and_dirty_writeback(self):
        cache = Cache(1, 16, MissLatency=4, MissIssueTime=2, record_requests=True)
        cache.request_access(1, 0, 0, 3)
        cache.advance(0)
        cache.advance(4)
        cache.consume_completion(3)

        cache.request_access(1, 16, 5, 4)
        cache.advance(5)

        self.assertEqual(cache.MEM_requests, [
            {"cycle": 0, "address": 0, "operation": "read_for_write",
             "instruction_index": 3, "instruction_indices": [3], "duration": 2},
            {"cycle": 5, "address": 0, "operation": "write",
             "instruction_index": None, "instruction_indices": [], "duration": 2},
        ])

    def test_fill_capacity_queues_misses_and_protects_a_completed_fill_for_one_cycle(self):
        cache = Cache(
            1, 8, MissLatency=4, MissIssueTime=2,
            fill_buffer_count=1, write_buffer_count=1,
        )
        self.assertEqual(cache.request_access(0, 8, 0, 0), "miss")
        self.assertEqual(cache.request_access(0, 16, 0, 1), "miss")
        cache.advance(0)

        self.assertEqual(len(cache.mshrs), 1)
        self.assertEqual(cache.get_request_state(0), "reading")
        self.assertEqual(cache.get_request_state(1), "queued_fill")
        self.assertEqual(cache.get_buffer_state()["fill"][0]["address"], 8)

        cache.advance(4)

        self.assertEqual(cache.get_request_state(0), "returned")
        self.assertEqual(cache.get_request_state(1), "queued_fill")
        self.assertEqual(cache.get_state(4)[0]["address"], 8)
        self.assertFalse(cache.get_state(4)[0]["loading"])
        return_fill = cache.get_buffer_state()["fill"][0]
        self.assertTrue(return_fill["valid"])
        self.assertEqual(return_fill["address"], 8)
        self.assertEqual(return_fill["state"], "returning")

        cache.consume_completion(0)
        self.assertFalse(cache.get_buffer_state()["fill"][0]["valid"])
        cache.advance(5)
        self.assertEqual(cache.get_request_state(1), "reading")
        self.assertEqual(cache.get_state(5)[0]["address"], 16)

    def test_fill_buffer_returns_data_after_cache_line_is_replaced(self):
        cache = Cache(
            1, 8, MissLatency=4, MissIssueTime=1,
            fill_buffer_count=2, return_throughput=1,
        )
        cache.request_access(0, 8, 0, 0)
        cache.request_access(0, 16, 0, 1)
        cache.advance(0)
        cache.advance(4)
        cache.advance(5)

        self.assertEqual(cache.get_request_state(0), "returned")
        self.assertEqual(cache.get_state(5)[0]["address"], 16)
        returning_fill = next(
            slot for slot in cache.get_buffer_state()["fill"] if slot["address"] == 8
        )
        self.assertEqual(returning_fill["state"], "returning")
        self.assertTrue(cache.consume_completion(0))
        self.assertFalse(any(
            slot["valid"] and slot["address"] == 8
            for slot in cache.get_buffer_state()["fill"]
        ))

    def test_pending_store_remains_dirty_if_its_cache_line_is_replaced(self):
        cache = Cache(
            1, 8, MissLatency=4, MissIssueTime=1,
            fill_buffer_count=2, write_buffer_count=1, return_throughput=1,
            record_requests=True,
        )
        cache.request_access(0, 8, 0, 0)
        cache.request_access(1, 8, 0, 1)
        cache.request_access(0, 16, 0, 2)
        cache.advance(0)
        cache.advance(4)
        self.assertTrue(cache.consume_completion(0))
        cache.advance(5)

        self.assertEqual(cache.get_request_state(1), "returned")
        self.assertEqual(cache.get_request_state(2), "waiting_writeback")
        self.assertTrue(any(
            request["operation"] == "write" and request["address"] == 8
            for request in cache.MEM_requests
        ))
        self.assertTrue(cache.consume_completion(1))

    def test_miss_to_block_already_in_flight_joins_existing_mm_request(self):
        cache = Cache(2, 8, MissLatency=4, MissIssueTime=2, record_requests=True)
        cache.request_access(0, 8, 0, 0)
        cache.advance(0)
        self.assertEqual(cache.request_access(0, 8, 1, 1), "secondary")
        cache.advance(1)

        self.assertEqual(len(cache.MEM_requests), 1)
        self.assertEqual(cache.MEM_requests[0]["instruction_indices"], [0, 1])
        self.assertEqual(cache.get_buffer_state()["fill"][0]["instruction_indices"], [0, 1])

    def test_timeline_limits_ordered_cache_returns_without_reissuing_loads(self):
        process = load_process()
        process.update({
            "Nloop": 1,
            "dispatch": 2,
            "nBlocks": 2,
            "blkSize": 4,
            "mPenalty": 4,
            "mIssueTime": 1,
        })
        process["instruction_list"][1]["source2"] = "A"

        timeline = json.loads(Scheduler().get_timeline(process, nret=2))
        first, second = timeline["instructions"]

        self.assertIn("!", first[4])
        self.assertIn("2", second[4])
        self.assertIn("@", second[4])
        self.assertIn("W", first[4])
        self.assertIn("W", second[4])
        self.assertTrue(any(
            slot["valid"]
            and slot["state"] == "returning"
            and slot["instruction_indices"] == [1]
            for snapshot in timeline["resource_usage"]["fill_buffers"]["snapshots"]
            for slot in snapshot["slots"]
        ))
        self.assertTrue(any(
            detail["reason"] == "cache-return"
            and detail["instruction_index"] == 1
            and detail["block_address"] == 0
            for detail in timeline["wait_details"]
        ))
        self.assertEqual(len(timeline["resource_usage"]["mm_requests"]), 1)
        self.assertEqual(
            timeline["resource_usage"]["mm_requests"][0]["instruction_indices"],
            [0, 1],
        )
        port_owners = timeline["resource_usage"]["port_owners"]["0"]
        self.assertEqual(sum(0 in rows for rows in port_owners), 1)
        self.assertEqual(sum(1 in rows for rows in port_owners), 1)
        self.assertEqual(first[4].count("L"), 1)
        self.assertEqual(second[4].count("L"), 1)
        self.assertEqual(second[4].count("@"), 1)

    def test_cache_state_reports_block_address_dirty_bit_and_pending_fill(self):
        cache = Cache(2, 8, MissLatency=4, MissIssueTime=2)

        self.assertFalse(cache.get_state(0)[0]["valid"])
        cache.request_access(1, 8, 0, 0)
        cache.advance(0)
        self.assertFalse(cache.consume_completion(0))
        self.assertEqual(cache.get_request_state(0), "reading")

        loading_line = cache.get_state(0)[0]
        self.assertEqual(loading_line["address"], 8)
        self.assertFalse(loading_line["dirty"])
        self.assertIsInstance(loading_line["lru"], int)
        self.assertTrue(loading_line["loading"])
        self.assertEqual(loading_line["ready_cycle"], 4)
        cache.advance(4)
        self.assertFalse(cache.get_state(4)[0]["loading"])
        self.assertTrue(cache.get_state(4)[0]["dirty"])
        self.assertTrue(cache.consume_completion(0))
        self.assertTrue(cache.get_state(4)[0]["dirty"])

    def test_read_hit_preserves_dirty_bit_for_a_later_writeback(self):
        cache = Cache(1, 8, MissLatency=4, MissIssueTime=2, record_requests=True)
        cache.request_access(1, 8, 0, 0)
        cache.advance(0)
        cache.advance(4)
        cache.consume_completion(0)

        result = cache.request_access(0, 8, 4, 1)

        self.assertEqual(result, "hit")
        self.assertTrue(cache.get_state(4)[0]["dirty"])
        cache.request_access(0, 16, 5, 2)
        cache.advance(5)
        self.assertTrue(any(
            request["operation"] == "write" and request["address"] == 8
            for request in cache.MEM_requests
        ))

    def test_cache_does_not_record_requests_outside_timeline_generation(self):
        cache = Cache(1, 16, MissLatency=10, MissIssueTime=4)
        cache.request_access(0, 0, 1, 0)

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
        self.assertEqual(resource_usage["fill_buffers"]["capacity"], 2)
        self.assertEqual(resource_usage["write_buffers"]["capacity"], 2)
        self.assertTrue(all(
            len(snapshot["slots"]) == 2
            for snapshot in resource_usage["fill_buffers"]["snapshots"]
        ))
        self.assertTrue(all(
            len(snapshot["slots"]) == 2
            for snapshot in resource_usage["write_buffers"]["snapshots"]
        ))
        self.assertIn(
            40,
            [line["address"] for snapshot in cache_state["snapshots"]
             for line in snapshot["lines"] if line["valid"]],
        )
        self.assertTrue(all(
            isinstance(request["address"], int)
            and request["operation"] in {"read", "read_for_write", "write"}
            and all(index < len(timeline["instructions"])
                    for index in request["instruction_indices"])
            for request in resource_usage["mm_requests"]
        ))
        self.assertTrue(all(
            timeline["instructions"][index][6] == request["address"]
            for request in resource_usage["mm_requests"]
            for index in request["instruction_indices"]
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
        store_rows = [
            row for row in timeline["instructions"] if "S" in row[4]
        ]
        cache_lines = [
            line
            for snapshot in timeline["resource_usage"]["cache_state"]["snapshots"]
            for line in snapshot["lines"]
            if line["valid"]
        ]

        self.assertTrue(store_rows)
        self.assertTrue(all("W" in row[4] for row in store_rows))
        self.assertIn(
            {"cycle": 2, "address": 0, "operation": "read_for_write",
             "instruction_index": 0, "instruction_indices": [0], "duration": 2},
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
        dirty_write_cycle = next(
            request["cycle"] for request in requests
            if request["operation"] == "write" and request["address"] == 0
        )
        replacement_read_cycle = next(
            request["cycle"] for request in requests
            if request["operation"] == "read_for_write" and request["address"] == 40
        )
        self.assertLess(dirty_write_cycle, replacement_read_cycle)
        self.assertTrue(any(line["dirty"] for line in cache_lines))

    def test_timeline_respects_configured_fill_and_write_buffer_capacities(self):
        process = load_process()
        process.update({
            "nBlocks": 2,
            "blkSize": 4,
            "mPenalty": 4,
            "mIssueTime": 2,
            "nFillBuffers": 1,
            "nWriteBuffers": 1,
        })
        for instruction in process["instruction_list"]:
            instruction["oper"] = "STORE"

        timeline = json.loads(Scheduler().get_timeline(process, nret=4))
        resources = timeline["resource_usage"]

        self.assertEqual(resources["fill_buffers"]["capacity"], 1)
        self.assertEqual(resources["write_buffers"]["capacity"], 1)
        self.assertTrue(all(
            sum(slot["valid"] for slot in snapshot["slots"]) <= 1
            for snapshot in resources["fill_buffers"]["snapshots"]
        ))
        self.assertTrue(all(
            sum(slot["valid"] for slot in snapshot["slots"]) <= 1
            for snapshot in resources["write_buffers"]["snapshots"]
        ))
        self.assertTrue(any(
            slot["valid"]
            for snapshot in resources["write_buffers"]["snapshots"]
            for slot in snapshot["slots"]
        ))
        read_cycles = [
            request["cycle"] for request in resources["mm_requests"]
            if request["operation"] != "write"
        ]
        self.assertTrue(all(
            later - earlier >= process["mIssueTime"]
            for earlier, later in zip(read_cycles, read_cycles[1:])
        ))

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
