import json
import unittest

from RVCAT.program import Program


def ports(*ps):
    mask = 0
    for p in ps:
        mask |= 1 << p
    return mask


def instr(text, destin, sources, latency, port_mask, type_="INT"):
    s = list(sources) + ["", "", ""]
    return {"type": type_, "oper": "ARITH" if type_ == "INT" else "", "size": "word",
            "text": text, "destin": destin, "source1": s[0], "source2": s[1], "source3": s[2],
            "latency": latency, "ports": port_mask, "stride": 1}


def analyse(instrs, dispatch, retire):
    process = {"name": "t", "ROBsize": 64, "dispatch": dispatch, "retire": retire,
               "instruction_list": instrs}
    return json.loads(Program().get_performance_analysis(process))


# Example of the performance-analysis guide (section 4):
#   for (i=0; i<N; i++) { R = T-2; T = J+A[i]; J = B[i]*R; }
GUIDE_EXAMPLE = [
    instr("R = T",        "R", ["T"],        2, ports(2, 3)),   # 0
    instr("R = R - Two",  "R", ["R", "Two"], 2, ports(2, 3)),   # 1
    instr("T = A[i]",     "T", ["i"],        4, ports(1, 3)),   # 2
    instr("T = T + J",    "T", ["T", "J"],   2, ports(2, 3)),   # 3
    instr("J = B[i]",     "J", ["i"],        4, ports(1, 3)),   # 4
    instr("i = i + 1",    "i", ["i"],        1, ports(0, 2)),   # 5
    instr("c = i != N",   "c", ["i", "N"],   1, ports(0, 2)),   # 6
    instr("J = J * R",    "J", ["J", "R"],   4, ports(2)),      # 7
    instr("if c go back", "",  ["c"],        1, ports(0), "BRANCH"),  # 8
]


class GuideExampleTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.result = analyse(GUIDE_EXAMPLE, dispatch=4, retire=5)

    def test_bounds_match_the_guide(self):
        self.assertEqual(self.result["LatencyTime"], 5)
        self.assertAlmostEqual(self.result["ThroughputTime"], 7 / 3)
        self.assertEqual(self.result["performance-bound"], "LATENCY")
        self.assertEqual(self.result["BestTime"], 5)

    def test_throughput_table_lists_the_relevant_resources(self):
        rows = {(b["resource"], tuple(b["ports"])): b for b in self.result["Throughput-Bounds"]}
        expected = {
            ("Dispatch", ()):         (list(range(9)), 9 / 4),
            ("Retire",   ()):         (list(range(9)), 9 / 5),
            ("Ports", (0,)):          ([8], 1),
            ("Ports", (1,)):          ([], 0),
            ("Ports", (2,)):          ([7], 1),
            ("Ports", (3,)):          ([], 0),
            ("Ports", (0, 2)):        ([5, 6, 7, 8], 2),
            ("Ports", (1, 3)):        ([2, 4], 1),
            ("Ports", (2, 3)):        ([0, 1, 3, 7], 2),
            ("Ports", (0, 2, 3)):     ([0, 1, 3, 5, 6, 7, 8], 7 / 3),
            ("Ports", (1, 2, 3)):     ([0, 1, 2, 3, 4, 7], 2),
            ("Ports", (0, 1, 2, 3)):  (list(range(9)), 9 / 4),
        }
        self.assertEqual(set(rows), set(expected))
        for key, (instrs, cycles) in expected.items():
            self.assertEqual(rows[key]["instructions"], instrs, key)
            self.assertAlmostEqual(rows[key]["cycles"], cycles, msg=key)
        bottlenecks = [k for k, b in rows.items() if b["bottleneck"]]
        self.assertEqual(bottlenecks, [("Ports", (0, 2, 3))])

    def test_excluded_instructions_report_their_other_ports(self):
        p0 = next(b for b in self.result["Throughput-Bounds"] if b["ports"] == [0])
        self.assertEqual(p0["excluded"], [{"index": 5, "other_ports": [2]},
                                          {"index": 6, "other_ports": [2]}])
        p023 = next(b for b in self.result["Throughput-Bounds"] if b["ports"] == [0, 2, 3])
        self.assertEqual(p023["excluded"], [{"index": 2, "other_ports": [1]},
                                            {"index": 4, "other_ports": [1]}])

    def test_latency_table_lists_the_cyclic_chains(self):
        chains = {tuple(b["instructions"]): b for b in self.result["Latency-Bounds"]}
        self.assertEqual(set(chains), {(5,), (0, 1, 7, 3)})
        self.assertEqual(chains[(5,)]["cycles"], 1)
        self.assertEqual(chains[(5,)]["variable"], "i")
        t_chain = chains[(0, 1, 7, 3)]
        self.assertEqual(t_chain["latencies"], [2, 2, 4, 2])
        self.assertEqual(t_chain["iterations"], 2)
        self.assertEqual(t_chain["cycles"], 5)
        self.assertEqual(t_chain["variable"], "T")
        self.assertTrue(t_chain["bottleneck"])
        self.assertFalse(chains[(5,)]["bottleneck"])


class ThroughputBoundsTests(unittest.TestCase):

    def test_dispatch_bound(self):
        result = analyse([instr("a", "a", [], 1, ports(0)), instr("b", "b", [], 1, ports(1)),
                          instr("br", "", [], 1, ports(2), "BRANCH")], dispatch=1, retire=4)
        dispatch = result["Throughput-Bounds"][0]
        self.assertEqual((dispatch["resource"], dispatch["cycles"], dispatch["bottleneck"]),
                         ("Dispatch", 3.0, True))

    def test_non_contiguous_port_combination(self):
        # 2 instructions on P0 or P2, plus the branch on P2: P0+P2 runs 3 instructions in 2 cycles
        result = analyse([instr("a", "a", [], 1, ports(0, 2)), instr("b", "b", [], 1, ports(0, 2)),
                          instr("c", "c", [], 1, ports(1)),
                          instr("br", "", [], 1, ports(2), "BRANCH")], dispatch=4, retire=4)
        self.assertEqual(result["ThroughputTime"], 1.5)
        bottlenecks = [(b["ports"], b["instructions"]) for b in result["Throughput-Bounds"]
                       if b["bottleneck"]]
        self.assertEqual(bottlenecks, [([0, 2], [0, 1, 3])])


if __name__ == "__main__":
    unittest.main()
