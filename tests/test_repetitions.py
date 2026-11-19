import json
import unittest

from RVCAT.scheduler import _scheduler

ALU, LD, FADD, BR = 0b11, 0b1100, 0b110000, 0b1000000


def I(text, type_, oper, size, destin, s1='', s2='', const='', lat=1, ports=ALU, stride=1):
    return dict(text=text, type=type_, oper=oper, size=size, destin=destin, source1=s1, source2=s2,
                source3='', constant=const, stride=stride, lanes=1, latency=lat, ports=ports)


# my_sum, scalar, unrolled 2 times by gcc (SUM-scalar): one accumulator
MY_SUM = [I('t0 = V[i]', 'MEM', 'LOAD', 'long', 't0', 'i', 'V', lat=5, ports=LD, stride=2),
          I('sum = sum + t0', 'FLOAT', 'ADD', 'double', 'sum', 'sum', 't0', lat=2, ports=FADD),
          I('t1 = V[i+1]', 'MEM', 'LOAD', 'long', 't1', 'i', 'V', const='1', lat=5, ports=LD, stride=2),
          I('sum = sum + t1', 'FLOAT', 'ADD', 'double', 'sum', 'sum', 't1', lat=2, ports=FADD),
          I('i = i + 2', 'INT', 'ARITH', 'word', 'i', 'i', const='2'),
          I('c = i != N', 'INT', 'ARITH', 'word', 'c', 'i', 'N'),
          I('if c go back', 'BRANCH', '', '', '', 'c', ports=BR, stride=2)]


def process(N=1000, nBlocks=16, **kw):
    p = dict(name='t', Nloop=N, dispatch=6, retire=8, ROBsize=200, sched='optimal', nBlocks=nBlocks,
             blkSize=64, mPenalty=12, mIssueTime=1, nFillBuffers=16, nWriteBuffers=16, rThru=2,
             instruction_list=MY_SUM)
    p.update(kw)
    return p


def results(N=1000, **kw):
    return json.loads(_scheduler.get_results(process(N, **kw), N // 2))


class RepetitionTest(unittest.TestCase):

    def test_one_repetition_is_the_simulation_of_before(self):
        before = results()
        self.assertEqual(results(rep=1), before)
        self.assertEqual(results(rep=1, repIndependent=False, repStrides={'V': 0}), before)

    def test_dynamic_dispatch_gives_the_same_results_as_the_static_one(self):
        # the repetitions use the dynamic dispatch: without repetitions it must simulate the same
        static, dynamic = results(), results(forceDynamic=True)
        for key in ('total_iterations', 'total_instructions', 'total_cycles', 'reads',
                    'read_primary_misses', 'read_secondary_misses', 'MM_Reads'):
            self.assertEqual(dynamic[key], static[key], key)
        self.assertEqual(dynamic['critical_path']['instructions'], static['critical_path']['instructions'])

    def test_totals_count_all_the_repetitions(self):
        one, three = results(), results(rep=3, repStrides={'V': 1000})
        self.assertEqual(three['total_iterations'], 3 * one['total_iterations'])
        self.assertEqual(three['total_instructions'], 3 * one['total_instructions'])
        self.assertEqual((three['repetitions'], three['iterations_per_repetition']), (3, 500))

    def test_the_same_data_are_found_in_the_cache_in_the_next_repetitions(self):
        # N = 64 doubles: 8 blocks, the cache has 16: only the first call misses
        r = results(N=64, rep=4, repStrides={'V': 0})
        self.assertEqual(r['read_primary_misses'], 8)
        self.assertEqual([m['primary'] for m in r['rep_misses']], [8, 0, 0, 0])

    def test_data_that_do_not_fit_miss_again_in_every_repetition(self):
        # N = 1,000 doubles: 125 blocks do not fit in 16: every call misses in every block
        r = results(rep=3, repStrides={'V': 0})
        self.assertEqual([m['primary'] for m in r['rep_misses']], [125, 125, 125])

    def test_new_data_in_each_repetition(self):
        # each repetition reads the next 1,000 elements (like the rows of a matrix)
        r = results(N=64, rep=4, repStrides={'V': 64})
        self.assertEqual([m['primary'] for m in r['rep_misses']], [8, 8, 8, 8])

    def test_independent_repetitions_overlap(self):
        # one chain of additions per call: independent calls overlap, dependent ones do not
        independent = results(N=100, rep=10, repIndependent=True, nBlocks=0)
        dependent = results(N=100, rep=10, repIndependent=False, nBlocks=0)
        single = results(N=100, nBlocks=0)
        self.assertLess(independent['total_cycles'], dependent['total_cycles'])
        self.assertLess(independent['total_cycles'], 10 * single['total_cycles'])
        self.assertGreaterEqual(dependent['total_cycles'], 10 * 50 * 4)   # 2 additions of 2 cycles per iteration

    def test_timeline_rows_know_their_repetition(self):
        t = json.loads(_scheduler.get_timeline(process(N=8, rep=3, nBlocks=0), nret=60))
        reps = [row[7]['rep'] for row in t['instructions']]
        self.assertEqual(sorted(set(reps)), [0, 1, 2])
        self.assertEqual(reps, sorted(reps))
        self.assertEqual((t['repetitions'], t['iterations_per_repetition']), (3, 4))

    def test_size_limits(self):
        with self.assertRaises(ValueError):
            results(N=1000, rep=21)                 # 21 × 500 iterations > 10,000
        results(N=1000, rep=20)                     # 20 × 500 = 10,000: allowed
        with self.assertRaises(ValueError):
            results(rep=0)
        with self.assertRaises(ValueError):
            results(rep=2, repStrides={'V': -1})


if __name__ == '__main__':
    unittest.main()
