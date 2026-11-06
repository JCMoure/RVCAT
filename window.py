from typing  import Optional
from enum    import Enum

class InstrState(Enum):
    DISPATCH        = "D"
    EXECUTE         = "E"
    LOAD            = "L"
    STORE           = "S"
    WRITE_BACK      = "W"
    RETIRE          = "R"
    WAIT_RESOURCE   = "*"
    WAIT_RETURN_QUEUE = "@"
    WAIT_RETIRE     = "-"
    WAIT_DATA       = "."
    WAIT_BANDWIDTH  = "^"
    WAIT_MM_REQUEST = "!"
    WAIT_MM_REQ_UPDT= "!"
    WAIT_MM_READY   = "#"
    WAIT_MM_RDY_UPDT= "#"
    WAIT_DATA_READY = ":"
    WAIT_CACHE_2ND  = "2"
    MM_UPDATE       = "U"
    SQUASHED        = "x"   # wrong-path instruction removed when the mispredicted branch resolves
    UNKNOWN         = "?"
    NONE            = " "

class InstrInstance:
    def __init__(self, dispatch_cycle: int, dynamic_idx: int, static_idx: int, mType: int, addr: int) -> None:
        self.d_idx    = dynamic_idx
        self.s_idx    = static_idx
        self.state    = InstrState.DISPATCH
        self.substate = InstrState.NONE
        self.port_used= None
        self.disp_cycle= dispatch_cycle      # clock cycle when instruction is dispatched
        self.exec_cycle= dispatch_cycle      # clock cycle when instruction beggins execution
        self.latency  = 0       # counter of cycles remainining for finishing execution
        self.memory   = mType   # 0 for non-memory instruction, 1 for load, 2 for store
        self.memAddr  = addr
        self.exec_lat = 0       # statistic of total execution latency, including waiting for resources
        self.waiting_for = []
        self.waiting_ports = []
        self.port_uses = []
        # programs with conditional branches (dynamic dispatch)
        self.iteration = None   # loop iteration of the instruction
        self.deps     = None    # dynamic indices of its producers (renaming at dispatch)
        self.wrong    = False   # dispatched on a wrong (speculative) path
        self.mispredicted = False   # conditional branch whose prediction fails
        self.checkpoint = None  # renaming table to restore when the misprediction resolves
        self.squashed_cycle = None

def __repr__(self) -> str:
        return f"{self.d_idx}: <{self.s_idx}, {self.cycle}>"

class Window:
    def __init__(self, size: int) -> None:
        self.count = 0
        self.first = 0
        self.last  = 0
        self.size  = size
        self.buffer= [None] * size
        self.by_id = {}         # dynamic index -> instruction in the window

    def is_full(self) -> bool:
        return self.count == self.size

    def is_empty(self) -> bool:
        return self.count == 0

    def get_instr(self, idx: int) -> Optional[InstrInstance]:
        first_idx = self.buffer[self.first].d_idx
        last_idx  = self.buffer[self.last-1].d_idx

        if first_idx <= idx and idx <= last_idx:
            return self.buffer[(self.first+idx-first_idx) % self.size]
        else:
            return None

    def push(self, disp_cycle:int, idx: int, instr: int, mType: int, addr: int) -> bool:
        if self.is_full():
            return False
        self.buffer[self.last] = (InstrInstance(disp_cycle, idx, instr, mType, addr))
        self.by_id[idx] = self.buffer[self.last]
        self.last = (self.last+1) % self.size
        self.count += 1
        return True

    def last_pushed(self) -> InstrInstance:
        return self.buffer[(self.last - 1) % self.size]

    def find(self, idx: int) -> Optional[InstrInstance]:
        # instruction with dynamic index idx, if it is in the window
        return self.by_id.get(idx)

    def truncate_after(self, idx: int) -> list:
        # remove (squash) the instructions younger than the one with dynamic index idx
        removed = []
        while self.count and self.buffer[(self.last - 1) % self.size].d_idx > idx:
            self.last = (self.last - 1) % self.size
            instr = self.buffer[self.last]
            self.by_id.pop(instr.d_idx, None)
            removed.append(instr)
            self.count -= 1
        removed.reverse()
        return removed

    def pop(self, n: int=1) -> bool:
        for _ in range(n):
            if self.count:
                self.by_id.pop(self.buffer[self.first].d_idx, None)
                self.first = (self.first+1) % self.size
                self.count -= 1
            else:
                return False
        return True

    def __getitem__(self, i: int) -> InstrInstance:
        if i in range(self.count):
            return self.buffer[(i+self.first) % self.size]
        else:
            raise IndexError

    def __repr__(self) -> str:
        out = ""
        for i in range(self.count):
            out += f"{self.buffer[(i+self.first) % self.size]}\n"
        return out
