import json
import unittest

from RVCAT.scheduler import _scheduler
from RVCAT.tests.test_repetitions import I, LD, BR

ST = 0b10000000
# a copy: a LOAD and a STORE per iteration; one fill buffer, a small cache and store buffer
COPY = [I('t = V[i]', 'MEM', 'LOAD', 'word', 't', 'i', 'V', lat=4, ports=LD),
        dict(text='W[i] = t', type='MEM', oper='STORE', size='word', destin='', source1='t', source2='W',
             source3='i', constant='', stride=1, lanes=1, latency=1, ports=ST),
        I('i = i + 1', 'INT', 'ARITH', 'word', 'i', 'i', const='1'),
        I('c = i != N', 'INT', 'ARITH', 'word', 'c', 'i', 'N'),
        I('if c go back', 'BRANCH', '', '', '', 'c', ports=BR)]


def process(**kw):
    p = dict(name='copy', Nloop=200, dispatch=4, retire=4, ROBsize=64, sched='optimal', nBlocks=4, blkSize=8,
             mPenalty=12, mIssueTime=4, nFillBuffers=1, nWriteBuffers=1, rThru=1, nStoreBuffers=4,
             instruction_list=COPY)
    p.update(kw)
    return p


class StoreBufferHeadTest(unittest.TestCase):

    def test_the_dynamic_timeline_writes_the_store_buffer_and_finishes(self):
        # the timeline stops at the last retired instruction: a LOAD still in flight must not keep the
        # only fill buffer, or the stores of the store buffer would never get it
        t = json.loads(_scheduler.get_timeline(process(forceDynamic=True), nret=100))
        snaps = t['resource_usage']['store_buffer']['snapshots']
        self.assertEqual(snaps[-1]['retired'], [])

    def test_the_snapshots_give_what_the_oldest_store_waits_for(self):
        for dynamic in (False, True):
            t = json.loads(_scheduler.get_timeline(process(forceDynamic=dynamic), nret=100))
            snaps = t['resource_usage']['store_buffer']['snapshots']
            states = {s['head_state'] for s in snaps}
            self.assertIn('queued_fill', states)          # no free fill buffer
            self.assertIn('reading', states)              # its block is coming
            for s in snaps:
                if not s['retired']:
                    self.assertIsNone(s['head_state'])


if __name__ == "__main__":
    unittest.main()
