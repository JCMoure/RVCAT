from typing       import Optional
from .instruction import Instruction
from .cache       import Cache

from pathlib      import Path
import importlib.resources
import json, os

PROCESSOR_PATH = importlib.resources.files("rvcat").joinpath("processors/")

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


    def list_processors_json(self) -> str:
        processors = [f.split('.')[:-1] for f in os.listdir(PROCESSOR_PATH) if f.endswith(".json")]
        return json.dumps(processors)


    def load_processor_json(self, data: dict) -> None:

       print("loading json processor");

        if isinstance(data, str):  # if it is a string convert to JSON struct
            try:
                cfg = json.loads(data)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON: {e}")
        else:
            cfg = data

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


    # Load JSON file containing processor specification
    def load_processor(self, file="") -> None:
        if file:
            json_path = PROCESSOR_PATH + f"{file}.json"
        else:
            json_path = PROCESSOR_PATH + "baseline.json"

        try:
           if not os.path.exists(json_path):
              raise FileNotFoundError(f"File not found: {json_path}")

           # Attempt to open the file
           with open(json_path, "r") as f:
               processor = json.load(f)
           self.load_processor_json(processor)
           return

        except FileNotFoundError as e:
           print(f"Error: {e}")
        except IOError as e:
           print(f"I/O Error while opening file: {e}")
        except Exception as e:
           print(f"Unexpected error: {e}")


    def import_processor_json(self, config: str) -> None:

        if isinstance(config, str):
            try:
                cfg = json.loads(config)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON: {e}")
        else:
            cfg = config

        out_path: Path = PROCESSOR_PATH.joinpath(f"{cfg['name']}.json")

        out_path.parent.mkdir(parents=True, exist_ok=True)

        with open(out_path, "w") as f:
            json.dump(cfg, f, indent=2)


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
