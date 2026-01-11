from .cache import Cache
from . import files
import json
 
global _processor

class Processor:

    def __init__(self) -> None:
        self.name      = ""
        self.stages    = {}
        self.resources = {}
        self.ports     = {}
        self.rports    = {}
        self.cache     = None
        self.nBlocks   = 0
        self.blkSize   = 0
        self.mPenalty  = 0
        self.mIssueTime= 0
        self.sched     = "greedy"


    # Load JSON file containing processor specification
    def load(self, file="") -> None:

        if file:
            json_name = f"{file}.json"
        else:
            json_name = "baseline.json"

        cfg = files.load_json ( json_name, True ) ## be sure is JSON struct

        if isinstance(cfg, str):  # if it is a string convert to JSON struct
            raise ValueError(f"Invalid JSON")

        self.name        = cfg.get("name", "")
        self.stages      = cfg.get("stages", {})
        self.resources   = cfg.get("resources", {})
        self.ports       = cfg.get("ports", {})
        self.rports      = cfg.get("rports", {})
        self.nBlocks     = cfg.get("nBlocks", 0)
        self.blkSize     = cfg.get("blkSize", 0)
        self.mPenalty    = cfg.get("mPenalty", 0)
        self.mIssueTime  = cfg.get("mIssueTime", 0)
        self.sched       = cfg.get("sched", "")
        self.cache       = None
        if self.nBlocks > 0:
            self.cache   = Cache(self.nBlocks, self.blkSize, self.mPenalty, self.mIssueTime)
        
        return json.dumps(self.__dict__())


    def save(self, name="") -> None:
        if name == "":
            name = self.name
        files.export_json( self.json(), name, True)


    def reset(self) -> None:
        if self.nBlocks > 0:
            self.cache.reset()


    def cache_access(self, mType, Addr, cycles):
        return self.cache.access(mType, Addr, cycles)


    def get_resource(self, instr_type: str):
        n = instr_type.count(".")

        instr_latency = None
        res_type = instr_type.upper()
        for i in range(n+1):
            if res_latency := self.resources.get(res_type):
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


    def json(self) -> str:
        return json.dumps(self.__dict__())


    def __repr__(self) -> str:
        return json.dumps(self.__dict__())


    def __dict__(self) -> dict:
        return {
            "name"      : self.name,
            "sched"     : self.sched,
            "stages"    : self.stages,
            "resources" : self.resources,
            "ports"     : self.ports,
            "rports"    : self.rports,
            "nBlocks"   : self.nBlocks,
            "blkSize"   : self.blkSize,
            "mPenalty"  : self.mPenalty,
            "mIssueTime": self.mIssueTime
        }

_processor = Processor()
