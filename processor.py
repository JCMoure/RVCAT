from .cache import Cache
import json
 
global _processor

class Processor:

    def __init__(self) -> None:
        self.name      = ""
        self.dispatch  = 1
        self.retire    = 1
        self.latencies = {}
        self.ports     = {}
        self.rports    = {}
        self.cache     = None
        self.nBlocks   = 0
        self.blkSize   = 0
        self.mPenalty  = 0
        self.mIssueTime= 0
        self.sched     = "greedy"


    # Load JSON objet containing processor specification
    def load(self, cfg) -> None:

        if isinstance(cfg, str):  # if it is a string convert to JSON struct
            raise ValueError(f"Invalid JSON")

        self.name        = cfg.get("name", "")
        self.dispatch    = cfg.get("dispatch", 1)
        self.retire      = cfg.get("retire", 1)
        self.latencies   = cfg.get("latencies", {})
        self.ports       = cfg.get("ports", {})
        self.nBlocks     = cfg.get("nBlocks", 0)
        self.blkSize     = cfg.get("blkSize", 0)
        self.mPenalty    = cfg.get("mPenalty", 0)
        self.mIssueTime  = cfg.get("mIssueTime", 0)
        self.sched       = cfg.get("sched", "")
        self.cache       = None
        if self.nBlocks > 0:
            self.cache   = Cache(self.nBlocks, self.blkSize, self.mPenalty, self.mIssueTime)

        self.rports = {}
        for port, instr_types in self.ports.items():
            for instr_type in instr_types:
                self.rports[instr_type]= []

        for port, instr_types in self.ports.items():
            for instr_type in instr_types:
                self.rports[instr_type].append(port)


    def cache_access(self, mType, Addr, cycles):
        return self.cache.access(mType, Addr, cycles)


    def get_resource(self, instr_type: str):
        n = instr_type.count(".")

        instr_latency = None
        res_type = instr_type.upper()
        for i in range(n+1):
            if res_latency := self.latencies.get(res_type):
                instr_latency = res_latency
                break
            elif i != n:
                res_type = res_type[:res_type.rindex(".")]

        instr_ports = None
        port_type = instr_type.upper()
        for i in range(n+1):
            if ports := self.rports.get(port_type):
                instr_ports = ports
                break
            elif i != n:
                port_type = port_type[:port_type.rindex(".")]

        if instr_latency and instr_ports:
            return instr_latency, instr_ports

        return 1,next(iter(self.ports))


    def __repr__(self) -> str:
        return json.dumps(self.__dict__())


    def __dict__(self) -> dict:
        return {
            "name"      : self.name,
            "sched"     : self.sched,
            "dispatch"  : self.dispatch,
            "retire"    : self.retire,
            "nBlocks"   : self.nBlocks,
            "blkSize"   : self.blkSize,
            "mPenalty"  : self.mPenalty,
            "mIssueTime": self.mIssueTime,
            "latencies" : self.resources,
            "ports"     : self.ports
        }

_processor = Processor()
