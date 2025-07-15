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


    def show_critical_path(self, n_iter= 1) -> str:

        n = self.n
        start_instrs   = []
        latencies      = []
        critical_paths = []
        dep_graph      = { i:[] for i in range(n*n_iter)}

        for i in range(n):
            if all(i <= j for j in self.dependencies[i].values()):
                start_instrs.append(i)

            for dep in self.dependencies[i].values():
               if dep >= i:
                   # i depends on instruction (dep) in previous loop iteration (loop-carried)
                   for q in range(n_iter-1):  # do not insert dependence on last loop iteration
                      dep_graph[dep+q*n].append(i+(q+1)*n)
               else:
                   # i depends on instruction (dep) in current loop iteration (not loop-carried)
                   for q in range(n_iter):  # insert dependence on all loop iterations
                      dep_graph[dep+q*n].append(i+q*n)

            resource = self.processor.get_resource(self.instructions[i][1].type)
            if not resource:
                latency = 1
            else:
                latency = resource[0]
            latencies.append(latency)

        max_latency = 0
        paths = [ [i] for i in start_instrs]  # instructions that do not depend on previous instructions
        while paths:
            path = paths.pop()
            last = path[-1]
            if not dep_graph[last]: # end of graph
                latency = sum(latencies[i%n] for i in path)
                if latency > max_latency:
                    max_latency = latency
                    critical_paths = [path]
                if latency == max_latency:
                    critical_paths.append(path)
            else:
                for dep in dep_graph[last]:
                    paths.append ( path + [dep] )

        out  = "###################################################################################\n"
        out += f"      **** Critical Path Analysis of n_iter={n_iter} loop iterations ***\n\n"
        out += f" Total Latency of critical path is {max_latency:0.2f} cycles\n\n"
        for path in critical_paths:
           out += f"\033[95m"
           for i in path[:-1]:
                id = i % n
                out += f"[{id}]{self.instructions[id][1].HLdescrp} "
                out += f"({latencies[id]} cycles) -> "

           id = path[-1] % n
           out += f"[{id}]{self.instructions[id][1].HLdescrp} "
           out += f"({latencies[id]} cycles)\n"
           out += f"\033[0m"

           out += f"      Total cycles = "
           if len(path)>1:
             for i in path[:-1]:
               out += f"{latencies[i%n]}+"
             out += f"{latencies[path[-1]%n]} = "

           out += f"{max_latency}\n\n"

        return out


    def show_static_performance_analysis(self) -> str:
        ports        = list( self.processor.ports.keys() )
        n_ports      = len ( ports )
        start_instrs = []
        latencies    = []
        resources    = []

        for i in range(self.n):
            if all(i <= j for j in self.dependencies[i].values()):
                start_instrs.append(i)

            resource = self.processor.get_resource(self.instructions[i][1].type)
            if not resource:
                latency = 1
            else:
                latency = resource[0]
            latencies.append(latency)
            instr_mask=0
            mask_bit=1
            for j in range(n_ports):
                if ports[j] in resource[1]:
                    instr_mask += mask_bit
                mask_bit *= 2
            resources.append(instr_mask)

        recurrent_paths = []
        paths   = [ [i]  for i in start_instrs]
        visited = { i:[] for i in range(self.n)}

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
                        if path not in recurrent_paths:
                            recurrent_paths.append(path)

        max_latency = 0
        for path in recurrent_paths:
            latency = sum(latencies[i] for i in path[:-1])
            iters = sum(a >= b for a,b in zip(path[:-1], path[1:]))
            latency_iter = latency / iters
            if latency_iter > max_latency:
                max_latency = latency_iter

        out  = "###################################################################################\n"
        out += " **** Static Analysis of Performance Limits due to Recurrent Data Dependences ***\n\n"
        out += f"  Latency-limit is {max_latency:0.2f} cycles/iteration\n\n"
        for path in recurrent_paths:
            latency = sum(latencies[i] for i in path[:-1])
            iters   = sum(a >= b for a,b in zip(path[:-1], path[1:]))
            latency_iter = latency / iters

            if latency_iter == max_latency:
              out += f"\033[95m  Critical "
            else:
              out += f"  Recurrent "

            out += f"path: "
            for i in path[:-1]:
                out += f"[{i}]{self.instructions[i][1].HLdescrp} "
                out += f"({latencies[i]} cycles) -> "

            out += f"[{path[-1]}]{self.instructions[path[-1]][1].HLdescrp}\n"

            out += f"      Total cycles = "
            if len(path)>2:
              for i in path[:-2]:
                out += f"{latencies[i]}+"
              out += f"{latencies[path[-2]]} = "

            out += f"{latency}  Total Iterations= {iters}\n\n"
 
            if latency_iter == max_latency:
                out += f"\033[0m"

        out += f" **** Static Analysis of Dispatch/Execute/Retire Bottlenecks ****\n"
        out += f"  Resources  \t Cycles/iter.\n"
        out += f"  ---------  \t-------------\n"

        dw_cycles = self.n / self.processor.stages["dispatch"]
        xw_cycles = self.n / self.processor.stages["execute"]
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

        max_cycles = max(port_cycles,dw_cycles, xw_cycles, rw_cycles)

        value_str = f"{dw_cycles:0.2f}" 
        if dw_cycles == max_cycles:
            out += f"\033[95m   dispatch \t{value_str:^13}\033[0m\n"
        else:
            out += f"   dispatch \t{value_str:^13}\n"

        value_str = f"{xw_cycles:0.2f}" 
        if xw_cycles == max_cycles:
            out += f"\033[95m   execute  \t{value_str:^13}\033[0m\n"
        else:
            out += f"   execute  \t{value_str:^13}\n"

        value_str = f"{rw_cycles:0.2f}" 
        if rw_cycles == max_cycles:
            out += f"\033[95m    retire  \t{value_str:^13}\033[0m\n"
        else:
            out += f"   retire  \t{value_str:^13}\n"

        for mask in range(1,n_combinations):
            uses = 0
            for instr_mask in resources: 
                if (mask & instr_mask) == instr_mask:
                     uses += 1
            cycles = uses / bin(mask).count("1")
            if cycles > 0:
                port_str = ""
                mask_bit=1
                for j in range(n_ports):
                    if mask_bit & mask == mask_bit:
                        port_str += f"{ports[j]} "
                    mask_bit *= 2

                value_str = f"{cycles:0.2f}" 
                if cycles == max_cycles:
                   out += f"\033[95m    {port_str:^9}\t{value_str:^13}\033[0m\n"
                else:
                   out += f"    {port_str:^9}\t{value_str:^13}\n"
        
        perf_bound= f"LATENCY-BOUND"
        if (max_latency > max_cycles):
            max_cycles= max_latency
        elif (max_latency < max_cycles):
            perf_bound= f"THROUGHPUT-BOUND"
        else:
            perf_bound += f" and THROUGHPUT-BOUND"

        out += f"\n Performance is {perf_bound}: {max_cycles:0.2f} cycles per iteration\n\n"
        out += "##################################################################################\n\n"
        return out



    def get_recurrent_paths_graphviz(self) -> str:
        colors = ["lightblue", "greenyellow", "lightyellow", "lightpink", "lightgrey", "lightcyan", "lightcoral"]
        start_instrs = []

        for i in range(self.n):
            if all(i <= j for j in self.dependencies[i].values()):
                start_instrs.append(i)

        recurrent_paths = []
        paths   = [ [i]  for i in start_instrs]
        visited = { i:[] for i in range(self.n)}

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
                        if path not in recurrent_paths:
                            recurrent_paths.append(path)

        # In recurrent paths we get all the critical paths in the format of [[3,
        # 3], [2, 0, 2]], where the numbers are the instructions.

        # Get the number of iterations to show the recurrent paths
        max_iters = 0
        for path in recurrent_paths:
            print(f'Curr path: {path}')
            curr_instr = path[0]
            local_max_iters = 0
            for instr in path[1:]:
                if curr_instr >= instr:
                    local_max_iters += 1
                curr_instr = instr
            if local_max_iters > max_iters:
                max_iters = local_max_iters
            print(f'Local max iters: {local_max_iters}')

        out = "digraph {\n"


        for iter_idx in range(1, max_iters+1):
            for ins_idx, instruction in self.instructions:

                out += f"iter{iter_idx}ins{ins_idx} [label=\"{instruction.HLdescrp}\", shape=\"box\", color={colors[iter_idx%len(colors)]}, style=filled];\n"

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
                        out += f"iter{iter_idx-1}ins{i_d} -> iter{iter_idx}ins{ins_idx}[label=\"{reg}\", color={curr_color}, penwidth=2.0];\n"
                        out += f"iter{iter_idx-1}ins{i_d} {'[style=invis]' if iter_idx == 1 else ''};\n"
                        if iter_idx == max_iters:
                            out += f"iter{iter_idx}ins{i_d} -> iter{iter_idx+1}ins{ins_idx}[label=\"{reg}\", color={curr_color}, penwidth=2.0];\n"
                            out += f"iter{iter_idx+1}ins{ins_idx} {'[style=invis]' if iter_idx == max_iters else ''};\n"
                        pass
                    else:
                        out += f"iter{iter_idx}ins{i_d} -> iter{iter_idx}ins{ins_idx}[label=\"{reg}\", color={curr_color}];\n"

        return out + "}\n"



    def show_dependencies(self) -> str:
        out = "··············· Program Description with Instruction Data-Dependences ························"
        for i, instruction in self.instructions:

            out += f"\n{i:{len(str(self.n))}}: "

            if instruction.HLdescrp != "":
                out += f"{instruction.HLdescrp:{self.pad}}: "
            else:
                out += f"{instruction}: "

            out += f"{instruction.action:32}: "

            for rs, i_d in self.dependencies[i].items():
                reg   = eval(f"self.instructions[{i}][1].{rs}")
                if i_d >= i:
                  out += f"<b>"

                out += f"{i_d} --> {reg}; "

                if i_d >= i:
                  out += f"</b>"

        out += "\n······························································································\n\n"
        return out



    def get_dependencies_grapviz(self, num_iters=5) -> str:

        # ----- BEGIN GET LONGEST PATH -----
        n = self.n
        start_instrs   = []
        latencies      = []
        critical_paths = []
        dep_graph      = { i:[] for i in range(n*num_iters)}

        for i in range(n):
            if all(i <= j for j in self.dependencies[i].values()):
                start_instrs.append(i)

            for dep in self.dependencies[i].values():
               if dep >= i:
                   # i depends on instruction (dep) in previous loop iteration (loop-carried)
                   for q in range(num_iters-1):  # do not insert dependence on last loop iteration
                      dep_graph[dep+q*n].append(i+(q+1)*n)
               else:
                   # i depends on instruction (dep) in current loop iteration (not loop-carried)
                   for q in range(num_iters):  # insert dependence on all loop iterations
                      dep_graph[dep+q*n].append(i+q*n)

            resource = self.processor.get_resource(self.instructions[i][1].type)
            if not resource:
                latency = 1
            else:
                latency = resource[0]
            latencies.append(latency)

        max_latency = 0
        paths = [ [i] for i in start_instrs]  # instructions that do not depend on previous instructions
        while paths:
            path = paths.pop()
            last = path[-1]
            if not dep_graph[last]: # end of graph
                latency = sum(latencies[i%n] for i in path)
                if latency > max_latency:
                    max_latency = latency
                    critical_paths = [path]
                if latency == max_latency:
                    critical_paths.append(path)
            else:
                for dep in dep_graph[last]:
                    paths.append ( path + [dep] )

        longest_path = critical_paths[0]

        print(f"Longest path: {longest_path}")

        # ----- END GET LONGEST PATH -----


        # ----- BEGIN GRAPHVIZ -----

        colors = ["lightblue", "greenyellow", "lightyellow", "lightpink", "lightgrey", "lightcyan", "lightcoral"]
        out = "digraph {\n"

        for iter_idx in range(num_iters):
            for ins_idx, instruction in self.instructions:
                out += f"iter{iter_idx}ins{ins_idx} [label=\"{instruction.HLdescrp}\", shape=\"box\", color={colors[iter_idx%len(colors)]}, style=filled];\n"

                for rs, i_d in self.dependencies[ins_idx].items():
                    reg   = eval(f"self.instructions[{ins_idx}][1].{rs}")

                    is_in_longest_path = False
                    for idx, i in enumerate(longest_path[:-1]):
                        if iter_idx == 0 and i_d == i and ins_idx == longest_path[idx+1]:
                            print(f"Found {i_d} -> {ins_idx}")
                            is_in_longest_path = True
                            break


                        dep_ins_longest_path_idx = self.n*iter_idx + i_d

                        if i_d >= ins_idx:
                            curr_ins_longest_path_idx = self.n*(iter_idx+1) + ins_idx
                        else:
                            curr_ins_longest_path_idx = self.n*iter_idx + ins_idx

                        print(f"Checking {i_d} -> {ins_idx}. Curr path {i} -> {longest_path[idx+1]}")
                        if dep_ins_longest_path_idx == (i) and curr_ins_longest_path_idx == (longest_path[idx+1]):
                            print(f"Found {dep_ins_longest_path_idx} (iter={iter_idx}, ins={i_d}) -> {curr_ins_longest_path_idx} (iter={iter_idx}, ins={ins_idx})")
                            is_in_longest_path = True
                            break

                    longest_path_str = ", color=red" if is_in_longest_path else ""

                    if i_d >= ins_idx:
                        out += f"iter{iter_idx}ins{i_d} -> iter{iter_idx+1}ins{ins_idx}[label=\"{reg}\", penwidth=2.0 {longest_path_str}];\n"
                    else:
                        out += f"iter{iter_idx}ins{i_d} -> iter{iter_idx}ins{ins_idx}[label=\"{reg}\" {longest_path_str}];\n"

        # Define nodes for the iteration after the last one
        for ins_idx, instruction in self.instructions:
            # Only if the instructions are part of a recurrent path
            p = False
            for rs, i_d in self.dependencies[ins_idx].items():
                if i_d >= ins_idx:
                    p = True
            if p:
                out += f"iter{num_iters}ins{ins_idx} [label=\"{instruction.HLdescrp}\", shape=\"box\"];\n"
        out += "}\n"
        out = out.replace('<--', '←')
        return out



    def annotate_action(self) -> str:
        out = "············· Program Description with Register-Level Transfer Language ······················"
        for i, instruction in self.instructions:
            out += f"\n{i:{len(str(self.n))}}: "
            if instruction.HLdescrp != "":
                out += f"{instruction.HLdescrp:{self.pad}}: "
            out += f"{instruction}: {instruction.action:32}"
            if instruction.LLdescrp != "":
                out += f": {instruction.LLdescrp:16}"
        out += "\n······························································································\n\n"
        return out



    def show_small_perf_analysis(self) -> str:

        ports        = list( self.processor.ports.keys() )
        n_ports      = len ( ports )
        start_instrs = []
        latencies    = []
        resources    = []

        for i in range(self.n):
            if all(i <= j for j in self.dependencies[i].values()):
                start_instrs.append(i)

            resource = self.processor.get_resource(self.instructions[i][1].type)
            if not resource:
                latency = 1
            else:
                latency = resource[0]
            latencies.append(latency)
            instr_mask=0
            mask_bit=1
            for j in range(n_ports):
                if ports[j] in resource[1]:
                    instr_mask += mask_bit
                mask_bit *= 2
            resources.append(instr_mask)

        recurrent_paths = []
        paths   = [ [i]  for i in start_instrs]
        visited = { i:[] for i in range(self.n)}

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
                        if path not in recurrent_paths:
                            recurrent_paths.append(path)

        max_latency = 0
        for path in recurrent_paths:
            latency = sum(latencies[i] for i in path[:-1])
            iters = sum(a >= b for a,b in zip(path[:-1], path[1:]))
            latency_iter = latency / iters
            if latency_iter > max_latency:
                max_latency = latency_iter

        dw_cycles = self.n / self.processor.stages["dispatch"]
        xw_cycles = self.n / self.processor.stages["execute"]
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

        max_cycles = max(port_cycles,dw_cycles, xw_cycles, rw_cycles)

        out = f"\n  Throughput-limit is {max_cycles:0.2f} cycles/iteration\n"

        value_str = f"{dw_cycles:0.2f}"
        if dw_cycles == max_cycles:
            out += f"   dispatch \t{value_str:^13}\n"

        value_str = f"{xw_cycles:0.2f}"
        if xw_cycles == max_cycles:
            out += f"   execute  \t{value_str:^13}\n"

        value_str = f"{rw_cycles:0.2f}"
        if rw_cycles == max_cycles:
            out += f"   retire  \t{value_str:^13}\n"

        for mask in range(1,n_combinations):
            uses = 0
            for instr_mask in resources:
                if (mask & instr_mask) == instr_mask:
                     uses += 1
            cycles = uses / bin(mask).count("1")
            if cycles == max_cycles:
                port_str = ""
                mask_bit=1
                for j in range(n_ports):
                    if mask_bit & mask == mask_bit:
                        port_str += f"P{ports[j]}+"
                    mask_bit *= 2

                value_str = f"{cycles:0.2f}"
                out += f"    {port_str[:-1]:^9}\t{value_str:^13}\n"

        out += f"\n  Latency-limit is {max_latency:0.2f} cycles/iteration\n"
        for path in recurrent_paths:
            latency = sum(latencies[i] for i in path[:-1])
            iters   = sum(a >= b for a,b in zip(path[:-1], path[1:]))
            latency_iter = latency / iters

            if latency_iter == max_latency:
                out += "    "
                for i in path[:-1]:
                    out += f"[{i}]({latencies[i]})-->"
                out += f"[{path[-1]}] : "
                out += f"("
                if len(path)>2:
                  for i in path[:-2]:
                    out += f"{latencies[i]}+"
                out += f"{latencies[path[-2]]})cycles / {iters} iter. = {latency_iter}\n"

        perf_bound= f"LATENCY-BOUND"
        if (max_latency > max_cycles):
            max_cycles= max_latency
        elif (max_latency < max_cycles):
            perf_bound= f"THROUGHPUT-BOUND"
        else:
            perf_bound += f" and THROUGHPUT-BOUND"
        out += f"\n Performance is {perf_bound}\n"

        return out


    def annotate_execution(self) -> str:
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
