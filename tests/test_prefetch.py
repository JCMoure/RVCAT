import json
import unittest

from RVCAT.cache import Cache
from RVCAT.scheduler import Scheduler


def sum_process(nBlocks=4, ROBsize=16, prefetchDistance=0, nFillBuffers=2):
    # sum = sum + V[i] (doubles): a LOAD with stride 8 bytes and a FLOAT addition
    return {
        "Nloop": 256, "ROBsize": ROBsize, "dispatch": 6, "retire": 6, "sched": "optimal",
        "nBlocks": nBlocks, "blkSize": 32, "mPenalty": 12, "mIssueTime": 1,
        "nFillBuffers": nFillBuffers, "nWriteBuffers": 2, "rThru": 2, "prefetchDistance": prefetchDistance,
        "instruction_list": [
            {"type": "MEM", "oper": "LOAD", "size": "long", "destin": "t", "source1": "i", "source2": "V",
             "source3": "", "constant": "", "stride": 1, "lanes": 1, "latency": 5, "ports": 4},
            {"type": "FLOAT", "oper": "ADD", "size": "double", "destin": "sum", "source1": "sum", "source2": "t",
             "source3": "", "constant": "", "latency": 2, "ports": 2},
            {"type": "INT", "oper": "ARITH", "size": "word", "destin": "i", "source1": "i", "source2": "",
             "source3": "", "constant": "1", "latency": 1, "ports": 1},
            {"type": "BRANCH", "oper": "", "size": "", "destin": "", "source1": "i", "source2": "",
             "source3": "", "constant": "", "stride": 1, "latency": 1, "ports": 8},
        ],
    }


def run(**kw):
    return json.loads(Scheduler().get_results(sum_process(**kw), 256))


class PrefetchTest(unittest.TestCase):

    def test_a_prefetch_brings_the_block_ahead_and_is_counted_useful_when_a_load_hits_it(self):
        cache = Cache(4, 32, MissLatency=12, MissIssueTime=1, fill_buffer_count=2, prefetch_distance=2)
        self.assertEqual(cache.request_access(0, 0, 0, 0), "miss")
        cache.prefetch(0, 8)                         # block 0 accessed: block 2 requested
        cache.advance(1)
        self.assertEqual(cache.prefetch_stats["issued"], 1)
        self.assertTrue(any(f["valid"] and f["prefetch"] and f["address"] == 64 for f in cache.get_buffer_state()["fill"]))
        for cycle in range(2, 20):
            cache.advance(cycle)
        self.assertEqual(cache.request_access(0, 64, 20, 1), "hit")
        self.assertEqual(cache.prefetch_stats["useful"], 1)

    def test_a_load_that_arrives_while_the_prefetched_block_is_on_the_way_is_a_late_prefetch(self):
        cache = Cache(4, 32, MissLatency=12, MissIssueTime=1, fill_buffer_count=2, prefetch_distance=1)
        cache.prefetch(0, 8)
        cache.advance(0)
        self.assertEqual(cache.request_access(0, 32, 1, 0), "secondary")
        self.assertEqual(cache.prefetch_stats["late"], 1)

    def test_a_prefetch_is_dropped_without_a_free_fill_buffer(self):
        cache = Cache(4, 32, MissLatency=12, MissIssueTime=1, fill_buffer_count=1, prefetch_distance=1)
        cache.request_access(0, 0, 0, 0)
        cache.prefetch(0, 8)
        cache.advance(0)
        self.assertEqual(cache.prefetch_stats["issued"], 0)
        self.assertEqual(cache.prefetch_stats["dropped"], 1)

    def test_prefetching_hides_the_latency_with_a_small_rob(self):
        without = run(prefetchDistance=0)
        with_pf = run(prefetchDistance=2)
        self.assertNotIn("prefetch", without)
        self.assertLess(with_pf["cycles_per_iteration"], 0.6 * without["cycles_per_iteration"])
        self.assertGreater(with_pf["prefetch"]["useful"], 0.9 * with_pf["prefetch"]["issued"])

    def test_a_distance_too_large_for_the_cache_evicts_the_prefetched_blocks_before_they_are_used(self):
        r = run(prefetchDistance=8)
        self.assertEqual(r["prefetch"]["useful"], 0)
        self.assertEqual(r["prefetch"]["unused"], r["prefetch"]["issued"])


if __name__ == "__main__":
    unittest.main()
