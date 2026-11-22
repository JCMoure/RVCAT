import json
import unittest

from RVCAT.scheduler import _scheduler
from RVCAT.tests.test_repetitions import process


def timeline(cache_lines, **kw):
    return json.loads(_scheduler.get_timeline(process(N=400, nBlocks=8, blkSize=8, **kw), nret=120,
                                              cache_lines=cache_lines))


class TimelineCacheLinesTest(unittest.TestCase):
    # cache_lines=False: no snapshots of the lines of the cache (the compact view of the web), and
    # the rest of the timeline does not change

    def check(self, **kw):
        full, light = timeline(True, **kw), timeline(False, **kw)
        self.assertTrue(full['resource_usage']['cache_state']['snapshots'])
        self.assertEqual(light['resource_usage']['cache_state']['snapshots'], [])
        self.assertEqual(light['resource_usage']['cache_state']['line_count'],
                         full['resource_usage']['cache_state']['line_count'])
        for key in ('instructions', 'producers', 'cycles'):
            self.assertEqual(light[key], full[key], key)
        for key in ('mm', 'mm_requests', 'fill_buffers', 'write_buffers', 'store_buffer'):
            self.assertEqual(light['resource_usage'][key], full['resource_usage'][key], key)
        self.assertLess(len(json.dumps(light)), len(json.dumps(full)))

    def test_static_dispatch(self):
        self.check()

    def test_dynamic_dispatch(self):
        self.check(forceDynamic=True)

    def test_by_default_the_lines_are_there(self):
        t = json.loads(_scheduler.get_timeline(process(N=400, nBlocks=8, blkSize=8), nret=60))
        self.assertTrue(t['resource_usage']['cache_state']['snapshots'])


if __name__ == "__main__":
    unittest.main()
