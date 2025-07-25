import configparser
import importlib.resources
import json
import os

from typing       import Optional
from .instruction import Instruction
from .cache       import Cache
from pathlib      import Path

PROCESSOR_PATH = importlib.resources.files("rvcat").joinpath("processors")

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
        processors = [f.split('.')[:-1] for f in os.listdir(PROCESSOR_PATH) if (f.endswith(".cfg") or f.endswith(".json"))]
        return json.dumps(processors)


    def load_processor_json(self, config: dict) -> None:
        config_json = json.loads(config)
        self.name        = config_json.get("name", "")
        self.stages      = config_json.get("stages", {})
        self.resources   = config_json.get("resources", {})
        self.ports       = config_json.get("ports", {})
        self.rports      = config_json.get("rports", {})
        self.nBlocks     = config_json.get("nBlocks", 0)
        self.blkSize     = config_json.get("blkSize", 0)
        self.mPenalty    = config_json.get("mPenalty", 0)
        self.mIssueTime  = config_json.get("mIssueTime", 0)
        self.sched       = config_json.get("sched", "")
        self.cache       = None
        if self.nBlocks > 0:
            self.cache   = Cache(self.nBlocks, self.blkSize, self.mPenalty, self.mIssueTime)


    def load_processor(self, name: str) -> None:

        proc_dir = PROCESSOR_PATH
        base, ext = Path(name).stem, Path(name).suffix.lower()

        # Build candidate paths
        cfg_path  = proc_dir / (base + ".cfg")
        json_path = proc_dir / (base + ".json")

        # If user explicitly passed .json, or .json exists and .cfg doesn't, load JSON
        if ext == ".json" or (json_path.exists() and not cfg_path.exists()):
            p = json_path if ext != ".json" else proc_dir / name
            if not p.exists():
                raise FileNotFoundError(f"JSON processor file not found: {p}")
            text = p.read_text()
            # this expects a JSON string
            self.load_processor_json(text)
            return

        p = cfg_path if ext != ".cfg" else proc_dir / name
        if not p.exists():
            raise FileNotFoundError(f"CFG processor file not found: {p}")
        config = configparser.ConfigParser(allow_no_value=True)
        with open(p, "r") as f:
            config.read_file(f)

        if "general" not in config:
            raise ValueError(f"No [general] section in {p}")

        self.name   = config.get("general", "name")
        self.sched  = config.get("general", "scheduler", fallback="greedy")

        self.stages = {stage:int(width) for stage,width
                                        in config["stage.width"].items()}
        self.resources = {
            resource.upper():int(latency) for resource, latency 
                                          in config["resource.latency"].items()
        }
        
        self.ports = {}
        for section in config.sections():
            if section.startswith("port."):
                port = section[5:]
                self.ports[port] = list(map(str.upper, config[section]))

        self.rports = {}
        for port, instrs in self.ports.items():
            for ins in instrs:
                self.rports.setdefault(ins, []).append(port)

        self.nBlocks   = int(config.get("cache", "numBlocks"))
        self.blkSize   = int(config.get("cache", "blockSize"))
        self.mPenalty  = int(config.get("cache", "missPenalty"))
        self.mIssueTime= int(config.get("cache", "missIssueTime"))

        self.cache = None
        if self.nBlocks > 0:
            self.cache = Cache(self.nBlocks, self.blkSize,
                               self.mPenalty, self.mIssueTime)

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
