import json
import unittest

from RVCAT.scheduler import _scheduler
from RVCAT.tests.test_repetitions import process


class TimelineProducersTest(unittest.TestCase):

    def test_each_row_lists_the_rows_whose_results_it_reads(self):
        t = json.loads(_scheduler.get_timeline(process(N=40), nret=14))
        self.assertEqual(len(t['producers']), len(t['instructions']))
        self.assertEqual(t['producers'][1], [0])        # sum = sum + t0 reads t0
        self.assertEqual(t['producers'][8], [3, 7])     # the next one: sum (previous) and its t0

    def test_the_dynamic_dispatch_gives_the_same_producers(self):
        static = json.loads(_scheduler.get_timeline(process(N=40), nret=14))['producers']
        dynamic = json.loads(_scheduler.get_timeline(process(N=40, forceDynamic=True), nret=14))['producers']
        self.assertEqual(static, dynamic)


if __name__ == "__main__":
    unittest.main()
