import json
import unittest

from RVCAT.program import Program
from RVCAT.scheduler import _scheduler

ALU, LD, ST, FADD, BR = 0b11, 0b100, 0b1000, 0b10000, 0b100000


def I(text, type_, oper, size, destin, s1='', s2='', s3='', const='', lat=1, ports=ALU, **kw):
    return dict(text=text, type=type_, oper=oper, size=size, destin=destin, source1=s1, source2=s2,
                source3=s3, constant=const, stride=1, lanes=1, latency=lat, ports=ports, **kw)


def f1(prob=0.5, mispredict=None, skip_load=False):
    # if (A[x] < B[x]) C[x] = A[x]   (optionally, a load of T only inside the conditional block)
    body = [I('a = A[x]', 'MEM', 'LOAD', 'word', 'a', 'x', 'A', lat=4, ports=LD),
            I('b = B[x]', 'MEM', 'LOAD', 'word', 'b', 'x', 'B', lat=4, ports=LD),
            I('t = a >= b', 'FLOAT', 'CMP', 'single', 't', 'a', 'b', lat=3, ports=FADD),
            I('if t skip 1', 'BRANCH', 'SKIP', '', '', 't', const='2' if skip_load else '1', ports=BR,
              prob=prob, mispredict=mispredict)]
    if skip_load:
        body.append(I('a = T[x]', 'MEM', 'LOAD', 'word', 'a', 'x', 'T', lat=4, ports=LD))
    return body + [I('C[x] = a', 'MEM', 'STORE', 'word', '', 'a', 'C', 'x', ports=ST),
                   I('x = x + 1', 'INT', 'ARITH', 'word', 'x', 'x', const='1'),
                   I('c = x != X', 'INT', 'ARITH', 'word', 'c', 'x', 'X'),
                   I('if c go back', 'BRANCH', '', '', '', 'c', ports=BR)]


def process(instrs, speculation='stall', nBlocks=0, penalty=10):
    return dict(name='t', Nloop=400, dispatch=4, retire=4, ROBsize=64, sched='optimal', nBlocks=nBlocks,
                blkSize=32, mPenalty=10, mIssueTime=1, bPenalty=penalty, speculation=speculation,
                instruction_list=instrs)


def results(instrs, **kw):
    return json.loads(_scheduler.get_results(process(instrs, **kw), 400))


class StaticAnalysisTest(unittest.TestCase):

    def test_paths_probabilities_and_producers(self):
        p = Program()
        p.load_instruction_list(f1(prob=0.3, skip_load=True))
        self.assertEqual(p.conditional_branches(), [(3, 2)])
        probs = p.execution_probabilities()
        self.assertAlmostEqual(probs[4], 0.7)
        self.assertAlmostEqual(probs[5], 0.7)
        self.assertAlmostEqual(probs[6], 1.0)
        # the store at 5 reads "a": only from instruction 4 (it is skipped together with it)
        self.assertEqual(p.producer_alternatives()[(5, 'a')], [(4, 0, 1.0)])

    def test_alternative_producers_have_probabilities(self):
        prog = f1(prob=0.3, skip_load=True)
        prog[3]['constant'] = '1'          # skips only the load of T: the store reads a from 4 or 0
        p = Program()
        p.load_instruction_list(prog)
        alts = {(w, d): round(prob, 3) for w, d, prob in p.producer_alternatives()[(5, 'a')]}
        self.assertEqual(alts, {(4, 0): 0.7, (0, 0): 0.3})

    def test_performance_analysis(self):
        a = json.loads(Program().get_performance_analysis(process(f1(prob=0.4, mispredict=0.2))))
        self.assertAlmostEqual(a['ExecProbability'][4], 0.6)
        self.assertAlmostEqual(a['MispredictionsPerIter'], 0.2)
        # cost of a misprediction: resolution (loads 4 + compare 3 + branch 1) + penalty 10
        self.assertEqual(a['Branches'][0]['resolution'], 8)
        self.assertAlmostEqual(a['MispredictTime'], 0.2 * (8 + 10))
        self.assertAlmostEqual(a['EstimatedTime'], a['BestTime'] + 3.6)
        # throughput: expected instructions (the store runs with probability 0.6), and range
        dispatch = a['Throughput-Bounds'][0]
        self.assertAlmostEqual(dispatch['expected'], 7.6)
        self.assertAlmostEqual(dispatch['cycles'], 7.6 / 4)
        self.assertEqual(a['ThroughputRange']['max'], 2.0)
        self.assertIn('LatencyRange', a)
        # the branch port runs two branches per iteration
        ports = [b for b in a['Throughput-Bounds'] if b['resource'] == 'Ports' and b['ports'] == [5]]
        self.assertEqual(ports[0]['cycles'], 2)

    def test_graph_has_probability_edges_and_control_edges(self):
        prog = f1(prob=0.3, skip_load=True)
        prog[3]['constant'] = '1'
        dot = Program().show_graphviz(prog, 1, True, False, False, True)
        self.assertIn('a 0.70', dot)
        self.assertIn('style=dotted', dot)
        self.assertIn('filled,dashed', dot)


class MaskedStoreTest(unittest.TestCase):

    def test_masked_store_depends_on_its_mask(self):
        prog = [I('m = a < b', 'VFLOAT', 'CMP', 'single', 'm', 'a', 'b', lat=3, ports=FADD),
                I('C[x:x+7] = a[0:7] if m[0:7]', 'VMEM', 'STORE', 'word', '', 'a', 'C', 'x', ports=ST, mask='m'),
                I('x = x + 8', 'INT', 'ARITH', 'word', 'x', 'x', const='8'),
                I('if c go back', 'BRANCH', '', '', '', 'c', ports=BR)]
        p = Program()
        p.load_instruction_list(prog)
        producers = [dep[0] for dep in p.inst_dependence_list[1] if dep[0] >= 0]
        self.assertIn(0, producers)
        self.assertEqual(p.read_variables(1), ['x', 'm'])


class DynamicSimulationTest(unittest.TestCase):

    def test_no_mispredictions_with_rate_zero(self):
        r = results(f1(prob=0.5, mispredict=0.0))
        self.assertEqual(r['branch']['mispredictions'], 0)
        self.assertEqual(r['total_iterations'], 400)
        # store executed in about half of the iterations: 7 or 8 instructions per iteration
        self.assertTrue(7 * 400 < r['total_instructions'] < 8 * 400)

    def test_mispredictions_cost_cycles_and_are_reproducible(self):
        base = results(f1(prob=0.5, mispredict=0.0))
        slow = results(f1(prob=0.5, mispredict=0.3))
        again = results(f1(prob=0.5, mispredict=0.3))
        self.assertEqual(slow, again)
        self.assertAlmostEqual(slow['branch']['mispredictions_per_iteration'], 0.3, delta=0.06)
        self.assertGreater(slow['total_cycles'], base['total_cycles'] + 0.3 * 400 * 10 * 0.8)

    def test_predictor_when_no_rate_is_given(self):
        r = results(f1(prob=0.95, mispredict=None))
        self.assertLess(r['branch']['mispredictions_per_iteration'], 0.15)

    def test_wrong_path_executes_and_is_squashed(self):
        stall = results(f1(mispredict=0.3), speculation='stall', nBlocks=4)
        wrong = results(f1(mispredict=0.3), speculation='wrong-path', nBlocks=4)
        self.assertEqual(stall['branch']['wrong_path_dispatched'], 0)
        self.assertGreater(wrong['branch']['wrong_path_dispatched'], 0)
        self.assertGreater(wrong['branch']['wrong_path_reads'], 0)
        self.assertEqual(wrong['total_instructions'], stall['total_instructions'])

    def test_wrong_path_cache_effects(self):
        prog = f1(prob=0.5, mispredict=0.3, skip_load=True)
        stall = results(prog, speculation='stall', nBlocks=16)
        wrong = results(prog, speculation='wrong-path', nBlocks=16)
        self.assertGreater(wrong['branch']['wrong_path_read_misses'], 0)
        self.assertNotEqual(wrong['read_misses'], stall['read_misses'])

    def test_timeline_rows_and_graph(self):
        t = json.loads(_scheduler.get_timeline(process(f1(mispredict=0.5), speculation='wrong-path'), 3, 30))
        rows = t['instructions']
        self.assertEqual(t['critical_path_graph']['node_count'], 3 * len(rows))
        self.assertTrue(any(r[7]['wrong'] and r[4].endswith('x') for r in rows))
        self.assertTrue(all(r[4].endswith('R') for r in rows if not r[7]['wrong']))


if __name__ == "__main__":
    unittest.main()
