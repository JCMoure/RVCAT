from typing      import Optional
from .instruction import MemType

from enum        import Enum

class InstrState(Enum):
    DISPATCH       = "D"
    EXECUTE        = "E"
    WRITE_BACK     = "W"
    RETIRE         = "R"
    WAIT_RESOURCE  = "*"
    WAIT_RETIRE    = "-"
    WAIT_DATA      = "."
    WAIT_BANDWIDTH = "*"
    WAIT_CACHE_MISS= "!"
    WAIT_CACHE_2ND = "2"
    UNKNOWN        = "?"
    NONE           = " "

class InstrInstance:

    def __init__(self, dispatch_cycle: int, dynamic_idx: int, static_idx: int, mType: MemType, addr: int) -> None:
        self.d_idx    = dynamic_idx
        self.s_idx    = static_idx
        self.state    = InstrState.DISPATCH
        self.substate = InstrState.NONE
        self.port_used= None
        self.disp_cycle= dispatch_cycle      # clock cycle when instruction is dispatched
        self.exec_cycle= dispatch_cycle      # clock cycle when instruction beggins execution
        self.latency  = 0       # counter of cycles remainining for finishing execution
        self.memory   = mType
        self.memAddr  = addr
        self.exec_lat = 0       # statistic of total execution latency, including waiting for resources

    def __repr__(self) -> str:
        return f"{self.d_idx}: <{self.s_idx}, {self.cycle}>"


class Window:

    def __init__(self, size: int) -> None:
        self.count = 0
        self.first = 0
        self.last  = 0
        self.size  = size
        self.buffer= [None] * size


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


    def push(self, disp_cycle:int, idx: int, instr: int, mType: MemType, addr: int) -> bool:
        if self.is_full():
            return False
        self.buffer[self.last] = (InstrInstance(disp_cycle, idx, instr, mType, addr))
        self.last = (self.last+1) % self.size
        self.count += 1
        return True


    def pop(self, n: int=1) -> bool:
        for _ in range(n):
            if self.count:
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
