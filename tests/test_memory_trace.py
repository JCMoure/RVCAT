import json
import unittest

from RVCAT.program import Program


def mem(oper, array, size="word", stride=1, lanes=1, constant="", type_="MEM"):
    return {"type": type_, "oper": oper, "size": size, "text": f"{oper} {array}",
            "destin": "x" if oper == "LOAD" else "", "source1": "i", "source2": array,
            "source3": "", "constant": constant, "stride": stride, "lanes": lanes}


def branch(S=1):
    return {"type": "BRANCH", "oper": "", "size": "", "text": "if c go back", "destin": "",
            "source1": "c", "source2": "", "source3": "", "constant": "", "stride": S, "lanes": 1}


def trace(instrs, N, K=2):
    return json.loads(Program().get_memory_trace({"instruction_list": instrs}, N, K))


class MemoryTraceTest(unittest.TestCase):

    def test_forward_arrays_placed_in_program_order(self):
        t = trace([mem("LOAD", "V"), mem("LOAD", "W"), branch()], N=10)
        self.assertEqual(t["iterations"], 10)
        self.assertEqual(t["shown"], [0, 1, 8, 9])
        self.assertEqual([a["name"] for a in t["arrays"]], ["V", "W"])
        self.assertEqual(t["arrays"][0]["bytes"], 40)
        self.assertEqual(t["arrays"][1]["base"], 40)
        v, w = t["accesses"]
        self.assertEqual(v["addr"], [0, 4, 32, 36])
        self.assertEqual(w["addr"], [40, 44, 72, 76])
        self.assertEqual(w["elem"], [0, 1, 8, 9])

    def test_vector_unrolled_and_backward(self):
        prog = [mem("LOAD", "A", lanes=4, stride=2, type_="VMEM"),
                mem("LOAD", "A", lanes=4, stride=2, constant="4", type_="VMEM"),
                mem("STORE", "B", size="long", stride=-1, lanes=4, constant="4", type_="VMEM"),
                branch(8)]
        t = trace(prog, N=35, K=1)              # N rounded down to 32 -> 4 iterations
        self.assertEqual((t["N"], t["S"], t["iterations"], t["shown"]), (32, 8, 4, [0, 3]))
        a0, a1, b = t["accesses"]
        self.assertEqual(a0["elem"], [0, 24])
        self.assertEqual(a1["elem"], [4, 28])
        self.assertEqual(b["elem"], [28, 16])    # N - c + k * L * s
        self.assertEqual(b["addr"][1] - b["addr"][0], 3 * 4 * 8 * -1)

    def test_same_addresses_as_the_scheduler(self):
        # The scheduler starts at inst.addr and adds byte_stride at each dispatch
        prog = [mem("LOAD", "X", size="byte", lanes=2, stride=3, constant="1", type_="VMEM"),
                mem("STORE", "Y", stride=0, constant="2"), branch(6)]
        t = trace(prog, N=60, K=20)
        p = Program()
        p.load_instruction_list(prog)
        p.assign_memory_addresses(60)
        for acc in t["accesses"]:
            inst = p.instruction_list[acc["index"]]
            self.assertEqual(acc["addr"], [inst.addr + k * inst.byte_stride for k in t["shown"]])

    def test_ignores_accesses_without_array(self):
        t = trace([mem("LOAD", ""), branch()], N=4)
        self.assertEqual(t["accesses"], [])


if __name__ == "__main__":
    unittest.main()
