from .instruction import Instruction, InstrFormat, MemType
from .processor   import Processor, _processor
from .parser      import Parser, Mnemonic, Operands, Description, Annotation
from pathlib      import Path

import importlib.resources
import json
import os

PROGRAM_PATH = importlib.resources.files("rvcat").joinpath("examples")

global _program

class Program:

    def __init__(self) -> None:
        self.instructions = []
        self.n            = 0
        self.loaded       = False
        self.name         = ""
        self.pad          = 0
        self.pad_type     = 0


    def import_program_json(self, data):
        if isinstance(data, str):
            try:
                cfg = json.loads(data)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON: {e}")
        else:
            cfg = data

        out_path: Path = PROGRAM_PATH.joinpath(f"{cfg['name']}.json")

        out_path.parent.mkdir(parents=True, exist_ok=True)

        with open(out_path, "w") as f:
            json.dump(cfg, f, indent=2)


    def load_program_json(self, data):

        print("loading json program");

        if isinstance(data, str):
            try:
                cfg = json.loads(data)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON: {e}")
        else:
            cfg = data

        self.name      = cfg.get("name", "")
        self.n         = cfg.get("n", 0)
        self.pad       = cfg.get("pad", 0)
        self.pad_type  = cfg.get("pad_type", 0)
        self.loaded    = True

        instrs = []
        for idx, entry in enumerate(cfg.get("instructions", [])):
            instr_dict = json.loads(entry) if isinstance(entry, str) else entry
            instr = Instruction.from_json(instr_dict)
            instrs.append((idx, instr))

        self.instructions = instrs
        self.n            = len(instrs)

        self.processor    = _processor
        self.processor.reset()
        self.dependencies     = {}
        self.dependency_graph = {i: [] for i, _ in instrs}
        self.generate_dependencies()


    def load_program(self, file="") -> None:
        if (file!=""):
            parser   = Parser()

            if file:
                json_path = PROGRAM_PATH.joinpath(f"{file}.json")
                asm_path  = PROGRAM_PATH.joinpath(f"{file}.s")

                if json_path.exists():
                    # load from JSON
                    with open(json_path, "r") as f:
                        cfg = json.load(f)
                    self.load_program_json(cfg)
                    return
                elif asm_path.exists():
                    self.name = str(asm_path)
                else:
                    raise FileNotFoundError(
                        f"Neither {json_path} nor {asm_path} exist."
                    )

            prg_list = parser.parse_file(self.name)

            self.instructions = []

            mnemonic = None
            operands = []
            HLdesc   = ""
            Annotate = []
            self.pad = 0
            self.pad_type= 0

            for item in prg_list:
                if type(item) == Mnemonic:
                    # Insert new instruction
                    if mnemonic != None:
                        self.instructions.append( Instruction( mnemonic, operands, HLdesc, Annotate ) )
                        self.pad_type = max( self.pad_type, len(self.instructions[-1].type))

                    operands = []
                    HLdesc   = ""
                    Annotate = []
                    mnemonic = item.name
                elif type(item) == Operands:
                    operands = item.name
                elif type(item) == Description:
                    HLdesc = item.name
                    self.pad = max(self.pad, len(HLdesc))
                elif type(item) == Annotation:
                    Annotate = item.name

            if mnemonic != None:
                self.instructions.append( Instruction( mnemonic, operands, HLdesc, Annotate ) )
                self.pad_type = max( self.pad_type, len(self.instructions[-1].type))

            self.loaded       = True
            self.instructions = list(enumerate(self.instructions))
            self.n            = len(self.instructions)

            self.processor    = _processor
            self.processor.reset()

            self.dependencies     = {}
            self.dependency_graph = {i:[] for i,_ in self.instructions}
            self.generate_dependencies()


    def json(self):
        return json.dumps(self.__dict__(), indent=2)
    

    def __dict__(self):
        data= {
            "n": self.n,
            "name": os.path.splitext(os.path.basename(self.name))[0],
            "pad": self.pad,
            "pad_type": self.pad_type
        }
        data["instructions"]=[]
        for instruction in self.instructions:
            data["instructions"].append(instruction[1].json())

        return data


    def list_programs_json(self) -> str:

        programs = ['.'.join(f.split('.')[:-1]) for f in os.listdir(PROGRAM_PATH) if (f.endswith(".s") or f.endswith(".json"))]
        return json.dumps(programs)


    def generate_dependencies(self) -> None:

        for i_1, instr_1 in self.instructions:
            instr_deps             = {}
            self.dependencies[i_1] = instr_deps

            if instr_1.format in [InstrFormat.UPPER_IMM, InstrFormat.JUMP]:
                continue

            ordered_instrs = self.instructions[:i_1][::-1]  + self.instructions[i_1:][::-1]

            for i_2, instr_2 in ordered_instrs:
                if (instr_1.format == InstrFormat.IMM and len(instr_deps) == 1):
                    break

                if (instr_1.format == InstrFormat.REG_REG_4):
                  if len(instr_deps) == 3:
                    break

                elif len(instr_deps) == 2:
                    break

                if instr_2.format in [InstrFormat.STORE, InstrFormat.BRANCH]\
                        or instr_2.rd.lower() in ["x0", "zero"]:
                    continue

                if instr_1.rs1.lower() == instr_2.rd.lower():
                    rs = "rs1"
                elif instr_1.rs2.lower() == instr_2.rd.lower():
                    rs = "rs2"
                elif instr_1.rs3.lower() == instr_2.rd.lower():
                    rs = "rs3"
                else:
                    continue

                if instr_deps.get(rs) != None:
                    continue
                instr_deps[rs] = i_2
                self.dependency_graph[i_2].append(i_1)


    def generate_dependence_info (self):
        n_static_instr = self.n

        # For each static instruction, list of dependent offsets
        # offset = positive number to subtract to my instruction ID to find dependent intr. ID
        DependenceEdges  = []

        for i in range(n_static_instr):
            dependents = self.dependencies[i].items()
            offsets = []
            for _, j in dependents:
                if j >= i: # loop carried dependency
                    offset = i - j + n_static_instr
                else:
                    offset = i - j
                offsets.append(offset)

            DependenceEdges.append(offsets)

        return DependenceEdges



    def get_cyclic_paths(self) -> list:
        
        # return list of cyclic dependence paths: [[3, 3], [2, 0, 2]], 
        #numbers are instr-IDs: same ID appears at begin & end

        start_instrs = []

        for i in range(self.n):
            if all(i <= j for j in self.dependencies[i].values()):
                start_instrs.append(i)

        cyclic_paths = []
        paths        = [ [i]  for i in start_instrs]
        visited       = { i:[] for i in range(self.n)}

        while paths:
            path = paths.pop()
            last = path[-1]
            for dep in self.dependency_graph[last]:
                if dep not in visited[last]:
                    paths.append(path+[dep])
                    visited[last].append(dep)
                else:
                    if len(set(path)) != len(path):
                        path = path[path.index(last):]
                        if path not in cyclic_paths:
                            cyclic_paths.append(path)

        return cyclic_paths  


    def get_instr_latencies(self) -> list:
        # return list of latencies for ordered list of instructions
        
        latencies = []

        for i in range(self.n):
            resource = self.processor.get_resource(self.instructions[i][1].type)
            if not resource:
                latency = 1
            else:
                latency = resource[0]
            latencies.append(latency)
    
        return latencies



    def get_instr_ports (self) -> list:
        # return list of port_usage masks for ordered list of instructions
 
        ports        = list( self.processor.ports.keys() )
        n_ports      = len ( ports )
        resources    = []

        for i in range(self.n):
            resource   = self.processor.get_resource(self.instructions[i][1].type)
            instr_mask = 0
            mask_bit   = 1
            for j in range(n_ports):
                if ports[j] in resource[1]:
                    instr_mask += mask_bit
                mask_bit *= 2
            resources.append(instr_mask)

        return resources



    def get_recurrent_paths_graphviz(self) -> str:

        colors = ["lightblue", "greenyellow", "lightyellow", "lightpink", "lightgrey", "lightcyan", "lightcoral"]

        recurrent_paths = self.get_cyclic_paths()
        latencies       = self.get_instr_latencies()

        max_latency    = 0   # maximum latency per iteration
        max_iters      = 0   # maximum number of iterations for cyclic path
        path_latencies = []  # latencies of cyclic paths

        for path in recurrent_paths:
            latency = sum(latencies[i] for i in path[:-1])
            iters   = sum(a >= b for a,b in zip(path[:-1], path[1:]))
            latency_iter = latency / iters
            path_latencies.append(latency_iter)
            if latency_iter > max_latency:
                max_latency = latency_iter
            max_iters = max( iters, max_iters )

        out = "digraph G {\nrankdir=\"TB\";splines=spline;newrank=true;\n"
        
        out += "edge [fontname=\"Consolas\"; fontsize=12; fontcolor=black];"

        for iter_idx in range(1, max_iters+1):
            out += f"subgraph c_{iter_idx} \{ style=\"filled,rounded\"; label = <<B>iteration #{iter_idx}</B>>;"
            out += f"labeljust=\"l\"; color=blue; fillcolor={colors[iter_idx-1]}; fontcolor=blue;"
            out += f"fontsize=\"18\"; fontname=\"Consolas\";\n"
            out += f"node [style=filled,shape=rectangle,fillcolor=lightgrey, fontname=\"Helvetica-Bold\"];"
            for ins_idx, instruction in self.instructions:
                lat = latencies[ins_idx]
                out += f"iter{iter_idx}ins{ins_idx} "
                out += f"[label=\"{ins_idx}:{instruction.HLdescrp}\n( {lat} )\"];\n"
            out += "}\n"
            
            for ins_idx, instruction in self.instructions:
                for rs, i_d in self.dependencies[ins_idx].items():
                    reg   = eval(f"self.instructions[{ins_idx}][1].{rs}")
              
                    # True if it's the first or last instruction of an iteration path
                    is_border = i_d >= ins_idx
                    
                    # In this case, the next instruction depends on the output of the current instr
                    # Check if the current path is part of a critical path
                    
                    is_recurrent = False
                    
                    for path in recurrent_paths:
                        curr = path[0]
                        next = path[1]
                        if ins_idx == next and i_d == curr :
                            is_recurrent = True
                            break
                        else:
                            for i in range(len(path)-2):
                                curr = next
                                next = path[i+2]
                                if next == ins_idx and curr == i_d:
                                    is_recurrent = True
                                    break

                    curr_color = "red" if is_recurrent else "black"
                    if is_border:
                        out += f"iter{iter_idx-1}ins{i_d} -> iter{iter_idx}ins{ins_idx}[label=\"{reg}\", "
                        out += f"color={curr_color}, penwidth=2.0];\n"
                        out += f"iter{iter_idx-1}ins{i_d} {'[style=invis]' if iter_idx == 1 else ''};\n"
                        if iter_idx == max_iters:
                            out += f"iter{iter_idx}ins{i_d} -> iter{iter_idx+1}ins{ins_idx}[label=\"{reg}\", "
                            out += f"color={curr_color}, penwidth=2.0];\n"
                            out += f"iter{iter_idx+1}ins{ins_idx} {'[style=invis]' if iter_idx == max_iters else ''};\n"
                        pass
                    else:
                        out += f"iter{iter_idx}ins{i_d} -> iter{iter_idx}ins{ins_idx}[label=\"{reg}\", color={curr_color}];\n"

        return out + "}\n"



    def show_performance_analysis(self) -> str:

        ports    = list( self.processor.ports.keys() )
        n_ports  = len ( ports )

        recurrent_paths = self.get_cyclic_paths()
        latencies       = self.get_instr_latencies()
        resources       = self.get_instr_ports()

        max_latency = 0
        for path in recurrent_paths:
            latency = sum(latencies[i] for i in path[:-1])
            iters   = sum(a >= b for a,b in zip(path[:-1], path[1:]))
            latency_iter = latency / iters
            if latency_iter > max_latency:
                max_latency = latency_iter

        dw_cycles = self.n / self.processor.stages["dispatch"]
        rw_cycles = self.n / self.processor.stages["retire"]

        # generate all combinations of ports
        n_combinations = 1
        for i in range(n_ports):
            n_combinations *= 2

        port_cycles = 0
        for mask in range(1,n_combinations):
            uses = 0
            for instr_mask in resources:
                if (mask & instr_mask) == instr_mask:
                     uses += 1
            cycles = uses / bin(mask).count("1")
            if port_cycles < cycles:
                port_cycles = cycles

        max_cycles = max(port_cycles, dw_cycles, rw_cycles)

        cycles_limit = max_cycles
        if (max_latency > max_cycles):
            perf_bound= "LATENCY-BOUND"
            cycles_limit = max_latency
        elif (max_latency < max_cycles):
            perf_bound= "THROUGHPUT-BOUND"
        else:
            perf_bound= "LATENCY- and THROUGHPUT-BOUND"
        out  = f"Performance is {perf_bound} and minimum execution time is {cycles_limit:0.2f} cycles per loop iteration\n"
        out += f" Throughput-limit is {max_cycles:0.2f} cycles/iteration\n"
        out += f"  Latency-limit   is {max_latency:0.2f} cycles/iteration\n"
        out += f"\n*** Throughput ********\n"

        tot=0;
        if dw_cycles == max_cycles:
           out += f"dispatch stage"
           tot = tot+1

        if rw_cycles == max_cycles:
           if (tot != 0):
              out += ", "
           tot = tot+1
           out += f"retire stage"

        for mask in range(1,n_combinations):
            uses = 0
            for instr_mask in resources:
                if (mask & instr_mask) == instr_mask:
                     uses += 1
            cycles = uses / bin(mask).count("1")
            if cycles == max_cycles:
                if (tot != 0):
                  out += ", "
                tot = tot+1
                port_str = ""
                mask_bit=1
                for j in range(n_ports):
                    if mask_bit & mask == mask_bit:
                        port_str += f"P{ports[j]}+"
                    mask_bit *= 2

                out += f"{port_str[:-1]}"

        out += f"\n\n"
        out += f"*** Cyclic Dependence Paths:\n"
        for path in recurrent_paths:
            latency = sum(latencies[i] for i in path[:-1])
            iters   = sum(a >= b for a,b in zip(path[:-1], path[1:]))
            latency_iter = latency / iters

            if latency_iter == max_latency:
                out += " "
                for i in path[:-1]:
                    out += f"[{i}] ({latencies[i]}) --> "
                out += f"[{path[-1]}] : "
                out += f"("
                if len(path)>2:
                  for i in path[:-2]:
                    out += f"{latencies[i]}+"
                out += f"{latencies[path[-2]]})cycles / {iters} iter. = {latency_iter}\n"

        return out


    def show_code(self) -> str:
        InsMessage = "INSTRUCTIONS"
        out = f"   {InsMessage:{self.pad}}     TYPE      LATENCY  EXECUTION PORTS\n"
        for i, instruction in self.instructions:
            instr_type = instruction.type
            resource = self.processor.get_resource(instr_type)
            if not resource:
                latency = 1
                ports = ()
            else:
                latency, ports = resource
            out += f"{i:{len(str(self.n))}}:"
            if instruction.HLdescrp != "":
                out += f"{instruction.HLdescrp:{self.pad}} : "
            out += f"{instr_type:{self.pad_type}} : {latency:^3} : "

            n = len(ports)
            for i in range(n-1):
              out += f"P{ports[i]},"

            out += f"P{ports[n-1]}\n"
        
        return out


    def show_instruction_memory_trace(self) -> str:
        out = ""
        if self.processor.nBlocks > 0:
            for i, instruction in self.instructions:
                if instruction.memory != MemType.NONE:
                    out += f"{i:{len(str(self.n))}}: {instruction.type:12}"
                    out += f" Init_ADDR={instruction.addr:4} Stride={instruction.stride:2} N={instruction.N:3}\n"
        return out


    def show_memory_trace(self) -> str:
        out = "····························· Memory Trace Description ···························"
        for i, instruction in self.instructions:
            if instruction.memory != MemType.NONE:
                out += f"\n{i:{len(str(self.n))}}: "
                if instruction.HLdescrp != "":
                   out += f"{instruction.HLdescrp:{self.pad}}: "
                else:
                   out += f"{instruction}: "
                out += f"{instruction.type:12} init_addr= {instruction.addr:3} stride= {instruction.stride:3} N= {instruction.N:3}"
        out += "\n···············································································\n\n"
        return out



    def instr_str(self, i: int) -> str:
        _, instruction = self.instructions[i]
        if instruction.HLdescrp != "":
            out = f"{instruction.HLdescrp:{self.pad}}"
        else:
            out = f"{instruction}"
        return out
 

    def instr_type_str(self, i: int) -> str:
        _, instruction = self.instructions[i]
        return f"{instruction.type}"


    def __repr__(self) -> str:
        out = ""
        for i, instruction in self.instructions:
            out += f"{i:{len(str(self.n))}}: {instruction}\n"
        return out

    def __getitem__(self, i: int) -> Instruction:
        return self.instructions[i%self.n][1]


_program = Program()
