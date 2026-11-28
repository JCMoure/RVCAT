import json
import unittest

from RVCAT.cache import Cache
from RVCAT.program import Program, Instruction
from RVCAT.scheduler import Scheduler


def I(type, oper, size, destin="", s1="", s2="", s3="", const="", latency=1, ports=1, **kw):
    return {"type": type, "oper": oper, "size": size, "destin": destin, "source1": s1, "source2": s2,
            "source3": s3, "constant": const, "latency": latency, "ports": ports, **kw}


def search_process(ahead=0, nFillBuffers=8, rep=4, N=12):
    # branchless binary search: b = (A[b+h] < key) ? b+h : b, with PREFETCHes of the next probes
    paths = {0: [], 1: ["L", "R"], 2: ["LL", "LR", "RL", "RR"]}[ahead]
    prefetches = [I("MEM", "PREFETCH", "word", "", "b", "A", "h", latency=5, ports=4,
                    stride=0, lanes=1, access="search", ahead=ahead, path=p) for p in paths]
    return {
        "Nloop": N, "ROBsize": 64, "dispatch": 6, "retire": 6, "sched": "optimal", "rep": rep,
        "nBlocks": 16, "blkSize": 64, "mPenalty": 12, "mIssueTime": 1, "bPenalty": 10,
        "nFillBuffers": nFillBuffers, "nWriteBuffers": 2, "rThru": 2,
        "instruction_list": [I("INT", "SHIFT", "word", "h", "n", const="1")] + prefetches + [
            I("MEM", "LOAD", "word", "t", "b", "A", "h", latency=5, ports=4, stride=0, lanes=1, access="search"),
            I("INT", "ARITH", "word", "lt", "t", "key"),
            I("INT", "ARITH", "word", "b", "lt", "b", "h"),
            I("INT", "ARITH", "word", "n", "n", "h"),
            I("INT", "ARITH", "word", "c", "n", const="1"),
            I("BRANCH", "", "", "", "c", stride=1, ports=8),
        ],
    }


def run(**kw):
    p = search_process(**kw)
    return json.loads(Scheduler().get_results(p, p["Nloop"] * p["rep"]))


class SearchAddressTest(unittest.TestCase):

    def program(self, d=10):
        prog = Program()
        prog.load_instruction_list(search_process()["instruction_list"])
        prog.assign_memory_addresses(d)
        return prog

    def test_the_load_probes_follow_a_binary_search_of_the_key(self):
        prog = self.program()
        load = next(i for i in prog.instruction_list if i.oper == "LOAD")
        for r in range(5):
            pos, lo, n = prog.search_position(r), 0, 1 << 10
            for k in range(10):
                h = n // 2
                self.assertEqual(prog.search_address(load, k, r), (lo + h) * 4)
                lo = lo + h if lo + h <= pos else lo
                n -= h
            self.assertEqual(lo, pos)

    def test_one_of_the_prefetches_requests_the_next_probe(self):
        prog = Program()
        prog.load_instruction_list(search_process(ahead=1)["instruction_list"])
        prog.assign_memory_addresses(10)
        load = next(i for i in prog.instruction_list if i.oper == "LOAD")
        pfs = [i for i in prog.instruction_list if i.oper == "PREFETCH"]
        for k in range(9):
            nxt = prog.search_address(load, k + 1, 0)
            self.assertEqual(sum(prog.search_address(p, k, 0) == nxt for p in pfs), 1)

    def test_the_fields_of_a_prefetch_are_read_and_written(self):
        inst = Instruction.from_json({"type": "MEM", "oper": "PREFETCH", "access": "search", "ahead": 2, "path": "LR"})
        self.assertEqual((inst.access, inst.ahead, inst.path), ("search", 2, "LR"))
        self.assertEqual(inst.json()["path"], "LR")


class SoftwarePrefetchTest(unittest.TestCase):

    def test_a_prefetch_that_misses_is_done_when_it_gets_a_fill_buffer_and_its_block_is_marked(self):
        cache = Cache(4, 32, MissLatency=12, MissIssueTime=1, fill_buffer_count=2)
        self.assertEqual(cache.request_access(4, 64, 0, 7), "miss")
        self.assertEqual(cache.get_request_state(7), "queued_fill")
        cache.advance(0)
        self.assertEqual(cache.get_request_state(7), "returned")
        self.assertTrue(cache.consume_completion(7))
        for cycle in range(1, 20):
            cache.advance(cycle)
        self.assertEqual(cache.sw_prefetch_stats["issued"], 1)
        self.assertEqual(cache.request_access(0, 64, 20, 8), "hit")
        self.assertEqual(cache.sw_prefetch_stats["useful"], 1)
        self.assertEqual(cache.prefetch_stats["useful"], 0)

    def test_a_prefetch_waits_for_a_fill_buffer(self):
        cache = Cache(4, 32, MissLatency=12, MissIssueTime=1, fill_buffer_count=1)
        cache.request_access(0, 0, 0, 1)
        cache.request_access(4, 64, 0, 2)
        cache.advance(0)
        self.assertEqual(cache.get_request_state(2), "queued_fill")

    def test_a_prefetch_of_a_block_in_the_cache_or_on_the_way_does_nothing(self):
        cache = Cache(4, 32, MissLatency=12, MissIssueTime=1, fill_buffer_count=2)
        cache.request_access(0, 0, 0, 1)
        self.assertEqual(cache.request_access(4, 8, 0, 2), "hit")
        self.assertEqual(cache.sw_prefetch_stats["executed"], 1)
        self.assertEqual(cache.sw_prefetch_stats["issued"], 0)

    def test_the_prefetches_hide_the_latency_of_the_search(self):
        base, pf1, pf2 = run(), run(ahead=1), run(ahead=2)
        self.assertNotIn("sw_prefetch", base)
        self.assertEqual(pf1["sw_prefetch"]["executed"], 2 * 12 * 4)
        self.assertEqual(pf1["reads"], base["reads"])            # a PREFETCH is not a read
        self.assertEqual(pf1["writes"], 0)                       # nor a store
        self.assertLess(pf1["total_cycles"], base["total_cycles"])
        self.assertGreater(pf2["sw_prefetch"]["useful"], pf1["sw_prefetch"]["useful"])
        self.assertLess(pf2["sw_prefetch"]["late"], pf1["sw_prefetch"]["late"])

    def test_the_timeline_marks_the_requests_of_the_prefetches(self):
        p = search_process(ahead=1, rep=1)
        out = json.loads(Scheduler().get_timeline(p, p["Nloop"], 200))
        requests = out["resource_usage"]["mm_requests"]
        self.assertTrue(any(r.get("prefetch") for r in requests))
        self.assertTrue(any(not r.get("prefetch") for r in requests))


if __name__ == "__main__":
    unittest.main()
