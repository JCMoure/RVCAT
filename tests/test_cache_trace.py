import json
import unittest

from RVCAT.program import Program


def I(type, oper, size, destin="", s1="", s2="", s3="", const="", **kw):
    return {"type": type, "oper": oper, "size": size, "destin": destin, "source1": s1, "source2": s2,
            "source3": s3, "constant": const, **kw}


LOOP = [I("INT", "ARITH", "word", "i", "i", const="1"), I("INT", "ARITH", "word", "c", "i", "N"),
        I("BRANCH", "", "", "", "c", stride=1)]


def base():
    # sum = sum + V[i] + W[i] (floats)
    return {"instruction_list": [I("MEM", "LOAD", "word", "t", "i", "V", stride=1, lanes=1),
                                 I("FLOAT", "ADD", "single", "s", "s", "t"),
                                 I("MEM", "LOAD", "word", "t", "i", "W", stride=1, lanes=1),
                                 I("FLOAT", "ADD", "single", "s", "s", "t")] + LOOP}


def mv(cols):
    # y[i] = A[i][:] · x (8×8 floats), one call per row; by columns: stride 8 and 1 element per call
    return {"rep": 8, "repStrides": {"A": 1 if cols else 8, "Y": 1},
            "instruction_list": [I("MEM", "LOAD", "word", "a", "j", "A", stride=8 if cols else 1, lanes=1),
                                 I("MEM", "LOAD", "word", "x", "j", "X", stride=1, lanes=1),
                                 I("FLOAT", "FMA", "single", "s", "a", "x", "s")] + LOOP,
            "epilogue": [I("MEM", "STORE", "word", "", "s", "Y", "i", stride=0, lanes=1)]}


def trace(prog, N, lines=4, blk=32, **kw):
    return json.loads(Program().get_cache_trace({**prog, **kw}, N, lines, blk))


class CacheTraceTest(unittest.TestCase):

    def test_two_streams_have_only_cold_misses(self):
        t = trace(base(), 64)
        self.assertEqual((t["totals"]["accesses"], t["totals"]["cold"], t["totals"]["capacity"]), (128, 16, 0))
        self.assertEqual([s["result"] for s in t["steps"][:4]], ["cold", "cold", "hit", "hit"])
        self.assertEqual(t["steps"][0]["array"], "V")
        self.assertEqual(t["steps"][16]["result"], "cold")          # V[8]: the second block of V

    def test_a_second_call_misses_again_when_the_data_do_not_fit(self):
        small = trace(base(), 64, rep=2)["totals"]
        large = trace(base(), 64, lines=16, rep=2)["totals"]
        self.assertEqual((small["cold"], small["capacity"]), (16, 16))
        self.assertEqual((large["cold"], large["capacity"]), (16, 0))

    def test_the_lru_line_is_replaced(self):
        t = trace(base(), 64)
        miss = next(s for s in t["steps"] if s["victim"] is not None)
        self.assertEqual(miss["victim"], 0)                          # the block of V[0], least recently used
        self.assertEqual(miss["elem"], 16)

    def test_the_stride_sets_the_fraction_of_misses(self):
        for stride, misses in ((1, 8), (3, 24), (8, 64)):
            prog = base()
            prog["instruction_list"] = [I("MEM", "LOAD", "word", "t", "i", "V", stride=stride, lanes=1)] + LOOP
            self.assertEqual(trace(prog, 64)["totals"]["cold"], misses)

    def test_a_matrix_by_columns_needs_a_line_for_each_column(self):
        rows = trace(mv(False), 8, lines=9)["totals"]
        cols9 = trace(mv(True), 8, lines=9)["totals"]
        cols10 = trace(mv(True), 8, lines=10)["totals"]
        self.assertEqual((rows["cold"], rows["capacity"]), (10, 0))
        self.assertEqual((cols9["cold"], cols9["capacity"]), (10, 63))
        self.assertEqual((cols10["cold"], cols10["capacity"]), (10, 0))
        self.assertGreater(cols9["writebacks"], 0)                   # the blocks of Y are dirty

    def test_the_steps_are_limited_but_the_totals_are_complete(self):
        t = json.loads(Program().get_cache_trace(base(), 64, 4, 32, 10))
        self.assertEqual(len(t["steps"]), 10)
        self.assertTrue(t["truncated"])
        self.assertEqual(t["totals"]["accesses"], 128)

    def test_prefetches_and_other_instructions_are_ignored(self):
        prog = base()
        prog["instruction_list"].insert(0, I("MEM", "PREFETCH", "word", "", "i", "V", stride=1, lanes=1))
        self.assertEqual(trace(prog, 64)["totals"]["accesses"], 128)

    def test_no_cache(self):
        with self.assertRaises(ValueError):
            Program().get_cache_trace(base(), 64, 0, 32)


if __name__ == "__main__":
    unittest.main()
