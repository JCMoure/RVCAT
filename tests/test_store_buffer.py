import json
import unittest

from RVCAT.scheduler import _scheduler
from RVCAT.tests.test_repetitions import I, BR

ST = 0b10000000
LD = 0b1100

# memset: a loop that only writes (8-byte elements, 8 per block of 64 bytes)
SET = [I('V[i] = x', 'MEM', 'STORE', 'long', '', 'x', 'V', lat=1, ports=ST),
       I('i = i + 1', 'INT', 'ARITH', 'word', 'i', 'i', const='1'),
       I('c = i != N', 'INT', 'ARITH', 'word', 'c', 'i', 'N'),
       I('if c go back', 'BRANCH', '', '', '', 'c', ports=BR)]


def process(N=400, **kw):
    p = dict(name='set', Nloop=N, dispatch=4, retire=4, ROBsize=64, sched='optimal', nBlocks=16,
             blkSize=64, mPenalty=40, mIssueTime=4, nFillBuffers=8, nWriteBuffers=8, rThru=1,
             nStoreBuffers=16, instruction_list=SET)
    p.update(kw)
    return p


def results(N=400, **kw):
    return json.loads(_scheduler.get_results(process(N, **kw), N))


class StoreBufferTest(unittest.TestCase):

    def test_a_store_miss_retires_without_waiting_for_its_block(self):
        t = json.loads(_scheduler.get_timeline(process(40), nret=8))
        stores = [row[4] for row in t['instructions'] if row[1] == 0]
        self.assertTrue(all(':' not in s and '!' not in s for s in stores))
        self.assertTrue(all(len(s) <= 5 for s in stores))          # D E W (-) R
        sb = t['resource_usage']['store_buffer']
        self.assertEqual(sb['capacity'], 16)
        # the retired stores wait in the store buffer for their block, and are written at the end
        self.assertTrue(any(snap['retired'] for snap in sb['snapshots']))
        self.assertEqual(sb['snapshots'][-1]['retired'], [])
        self.assertGreaterEqual(t['cycles'], 40)                    # the block arrives after 40 cycles

    def test_the_store_buffer_and_not_the_rob_limits_a_loop_of_stores(self):
        small, large = results(nStoreBuffers=8), results(nStoreBuffers=64)
        self.assertGreater(small['total_cycles'], 2 * large['total_cycles'])
        self.assertGreater(small['store_buffer_full_cycles'], 0)
        self.assertEqual(results(nStoreBuffers=16, ROBsize=32)['total_cycles'],
                         results(nStoreBuffers=16, ROBsize=128)['total_cycles'])

    def test_stores_do_not_use_the_return_throughput(self):
        self.assertEqual(results(rThru=1)['total_cycles'], results(rThru=8)['total_cycles'])

    def test_every_store_miss_reads_its_block_before_the_end(self):
        r = results()
        self.assertEqual(r['write_primary_misses'], 400 // 8)
        self.assertEqual(r['MM_Reads'], r['write_primary_misses'])
        self.assertEqual(r['writes'], 400)

    def test_without_cache_there_is_no_store_buffer(self):
        a, b = results(nBlocks=0, nStoreBuffers=1), results(nBlocks=0, nStoreBuffers=64)
        self.assertEqual(a['total_cycles'], b['total_cycles'])
        self.assertEqual(a['store_buffer_full_cycles'], 0)

    def test_loads_still_wait_for_their_block(self):
        load = [I('t = V[i]', 'MEM', 'LOAD', 'long', 't', 'i', 'V', lat=1, ports=LD)] + SET[1:]
        t = json.loads(_scheduler.get_timeline(process(40, instruction_list=load), nret=4))
        self.assertIn(':', t['instructions'][0][4])

    def test_size_limits(self):
        for bad in (0, 257, 1.5, True):
            with self.assertRaises(ValueError):
                results(nStoreBuffers=bad)


if __name__ == "__main__":
    unittest.main()
