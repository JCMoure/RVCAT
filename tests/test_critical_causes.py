import json
import unittest

from RVCAT.scheduler import _scheduler
from RVCAT.tests.test_repetitions import I, BR

LD1 = 0b100        # a single port for the loads
# two loads per iteration and one port: the second one waits for the port (*)
TWO_LOADS = [I('a = V[i]', 'MEM', 'LOAD', 'word', 'a', 'i', 'V', lat=3, ports=LD1),
             I('b = W[i]', 'MEM', 'LOAD', 'word', 'b', 'i', 'W', lat=3, ports=LD1),
             I('s = a + b', 'INT', 'ARITH', 'word', 's', 'a', 'b'),
             I('i = i + 1', 'INT', 'ARITH', 'word', 'i', 'i', const='1'),
             I('c = i != N', 'INT', 'ARITH', 'word', 'c', 'i', 'N'),
             I('if c go back', 'BRANCH', '', '', '', 'c', ports=BR)]


def process(**kw):
    p = dict(name='two', Nloop=200, dispatch=4, retire=4, ROBsize=16, sched='optimal', nBlocks=2, blkSize=8,
             mPenalty=12, mIssueTime=4, nFillBuffers=1, nWriteBuffers=1, rThru=1, nStoreBuffers=4,
             instruction_list=TWO_LOADS)
    p.update(kw)
    return p


def timeline(**kw):
    return json.loads(_scheduler.get_timeline(process(**kw), nret=120))


class CriticalCausesTest(unittest.TestCase):
    # the timeline says who holds back a waiting instruction (the critical path of the web)

    def each_dispatch(self):
        for dynamic in (False, True):
            for sched in ('optimal', 'greedy'):
                yield dynamic, sched, timeline(forceDynamic=dynamic, sched=sched)

    def test_a_wait_for_a_port_names_who_had_it(self):
        for dynamic, sched, t in self.each_dispatch():
            # (the rows of the timeline: the ones after its last instruction are not in it)
            waits = [d for d in t['wait_details'] if d['reason'] == 'ports' and d['instruction_index'] < len(t['instructions'])
                     and d['cycle'] < t['cycles']]
            self.assertTrue(waits, (dynamic, sched))
            owners = t['resource_usage']['port_owners']
            for d in waits:
                self.assertTrue(d['blockers'], (dynamic, sched, d))
                for b in d['blockers']:          # the blocker started in one of those ports in that cycle
                    self.assertTrue(any(b in owners[str(p)][d['cycle']] for p in d['ports']), (dynamic, sched, d))

    def test_the_stops_of_the_dispatch_are_recorded(self):
        for dynamic, sched, t in self.each_dispatch():
            stalls = t['dispatch_stalls']
            reasons = {s['reason'] for s in stalls}
            self.assertIn('rob', reasons, (dynamic, sched))       # a small ROB and misses
            self.assertIn('width', reasons, (dynamic, sched))
            rows = t['instructions']
            for s in stalls:
                # the oldest one (in the timeline): it has not retired yet
                if s['reason'] == 'rob' and s['blocker'] is not None and s['blocker'] < len(rows):
                    start, states = rows[s['blocker']][2], rows[s['blocker']][4]
                    self.assertGreaterEqual(start + states.index('R'), s['cycle'], (dynamic, sched, s))

    def test_a_miss_admitted_late_says_which_fill_buffer_was_freed(self):
        for dynamic, sched, t in self.each_dispatch():
            admitted = [q['admission'] for q in t['resource_usage']['mm_requests'] if q.get('admission')]
            self.assertTrue(admitted, (dynamic, sched))
            freed = [a['fill_freed'] for a in admitted if a['fill_freed']]
            self.assertTrue(freed, (dynamic, sched))
            for a in admitted:
                self.assertGreater(a['cycle'], a['requested'])

    def test_the_results_do_not_record_them(self):
        r = json.loads(_scheduler.get_results(process(), 100))
        self.assertNotIn('dispatch_stalls', r)
        self.assertIsNone(_scheduler.dispatch_stalls)


if __name__ == "__main__":
    unittest.main()
