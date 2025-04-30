import configparser
import importlib.resources
import json
import os

from typing       import Optional
from .instruction import Instruction
from .cache       import Cache
from .isa         import _isa

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


    def list_processors_json(self) -> str:
        processors = [f.split('.')[:-1] for f in os.listdir(PROCESSOR_PATH) if f.endswith(".cfg")]
        return json.dumps(processors)


    def load_processor(self, name: str) -> None:

        config = configparser.ConfigParser(allow_no_value=True)

        file = f"{PROCESSOR_PATH}/{name}.cfg"
        with open(file, "r") as f:
            config.read_file(f)

        if "general" not in config:
            return

        self.name   = config.get("general", "name")
        self.sched  = config.get("general", "scheduler", fallback="greedy")

        self.stages = {stage:int(width) for stage,width
                                        in config["stage.width"].items()}
        self.resources = {
            resource.upper():int(latency) for resource, latency 
                                          in config["resource.latency"].items()
        }
        
        self.ports = {}
        ports = [section for section in config.sections() 
                         if section.startswith("port.")]

        for port in ports:
            self.ports[port[5:]] = list(map(str.upper, config[port]))

        self.rports = {}
        for port, instr_types in self.ports.items():
            for instr_type in instr_types:
                self.rports[instr_type]= []
        
        for port, instr_types in self.ports.items():
            for instr_type in instr_types:
                self.rports[instr_type].append(port)

        self.nBlocks   = int(config.get("cache", "numBlocks"))
        self.blkSize   = int(config.get("cache", "blockSize"))
        self.mPenalty  = int(config.get("cache", "missPenalty"))
        self.mIssueTime= int(config.get("cache", "missIssueTime"))

        self.cache     = None
        if self.nBlocks > 0:
            self.cache = Cache(self.nBlocks, self.blkSize, self.mPenalty, self.mIssueTime)

        isas = config.get("general", "isas", fallback="").split(",")
        for isa in isas:
            _isa.load_isa(isa.strip())


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
            "stages"    : self.stages,
            "resources" : self.resources,
            "ports"     : self.ports,
            "rports"    : self.rports,
            "nBlocks"   : self.nBlocks,
            "blkSize"   : self.blkSize,
            "mPenalty"  : self.mPenalty,
            "mIssueTime": self.mIssueTime
        }

    def __repr__(self) -> str:

        out = f"+++++++++++++++++++++++++++++++++++++++++++++++++++++++\nPROCESSOR name is {self.name}\n"

        for stage, width in self.stages.items():
            out += f"  {stage} width = {width}\n"

        out += f"\n  Scheduler = {self.sched}\n\n"

        if self.nBlocks > 0:
            out += f"  CACHE  Blocks={self.nBlocks}  "
            out += f"BlkSize={self.blkSize}  "
            out += f"MissPenalty={self.mPenalty}  "
            out += f"MissIssueTime={self.mIssueTime}\n\n"

        out += f"   Instruction Type    Latency\n"
        out += f"   ----------------   ----------\n"

        for resource, ports in self.rports.items():
            latency = self.resources[resource]
            out += f"     {resource:16}  {latency:^2} cycles\n"

        out += f"\n   Execution Port    Instruction Types\n"
        out += f"   --------------    -----------------\n"
        for port in self.ports:
            out += f"       P.{port:10}  {self.ports[port]}\n"

        out += "\n++++++++++++++++++++++++++++++++++++++++++++++++++++++\n\n"
        return out


_processor = Processor()
_processor.load_processor("baseline")
