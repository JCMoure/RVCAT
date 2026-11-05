import unittest

from RVCAT.exec_graph import old_priority


class PortAssignmentTest(unittest.TestCase):

    def test_issues_as_many_instructions_as_possible(self):
        # An older ADD (ports 1, 5) and two conversions (ports 0, 1): the ADD must take port 5
        self.assertEqual(old_priority({0: [1, 5], 1: [0, 1], 2: [0, 1]}), {0: 5, 1: 0, 2: 1})

    def test_prefers_older_instructions(self):
        # Three instructions for two ports: the two oldest issue
        self.assertEqual(sorted(old_priority({3: [0, 1], 7: [0, 1], 9: [0, 1]})), [3, 7])

    def test_empty_and_impossible(self):
        self.assertEqual(old_priority({}), {})
        self.assertEqual(old_priority({4: []}), {})


if __name__ == "__main__":
    unittest.main()
