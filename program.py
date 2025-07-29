from .instruction import Instruction
from .processor   import Processor, _processor
from pathlib      import Path

import importlib.resources
import json, os


PROGRAM_PATH = importlib.resources.files("rvcat").joinpath("examples")


class Program:

    def __init__(self) -> None:

        # data loaded/stored which do not change during execution
        self.name             = ""
        self.n                = 0
        self.instruction_list = []

        # data generated when loading a new program. Do not need to save it
        self.loaded       = False
        self.variables    = [] # variable names (each appears only once, in program order)
        self.constants    = [] # constant values/variable names (only once, program order)
        self.read_only    = [] # list of read-only variable names (only once)

        self.loop_carried = [] # list of tuples of loop-carried variables: (producer_id,var_name)

        self.inst_dependence_list = []  ## list of instruction data dependencies
        self.dependence_edges     = []  ## list of dependence offsets
        self.cyclic_paths         = []  # list of cyclic paths (a list of inst_ids)


    # return JSON structure of current program
    def json(self):
        return json.dumps(self.__dict__(), indent=2)


    # return JSON values of current program-class instance
    def __dict__(self):
        data = {
            "name": os.path.splitext(os.path.basename(self.name))[0],
            "n":    self.n,
        }
        data["instruction_list"]=[]
        for instruction in self.instruction_list:
            data["instruction_list"].append(instruction.json())

        return data


    # write program to disk, either JSON structure or String specifying Json
    def import_program_json(self, data):

        if isinstance(data, str):  # if data is a string, convert to JSON structure
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


    # return JSON structure containing names of programs found in PROGRAM_PATH
    def list_programs_json(self) -> str:
        p = ['.'.join(f.split('.')[:-1]) for f in os.listdir(PROGRAM_PATH) if f.endswith(".json")]
        return json.dumps(p)


    # Load JSON file containing program specification
    def load_program(self, file="") -> None:
        if file:
            json_path = PROGRAM_PATH + f"{file}.json"
        else:
            json_path = PROGRAM_PATH + "baseline.json"

        try:
           if not os.path.exists(json_path):
              raise FileNotFoundError(f"File not found: {json_path}")

           # Attempt to open the file
           with open(json_path, "r") as f:
               program = json.load(f)
           self.load_program_json(program)
           return

        except FileNotFoundError as e:
           print(f"Error: {e}")
        except IOError as e:
           print(f"I/O Error while opening file: {e}")
        except Exception as e:
           print(f"Unexpected error: {e}")


    # load JSON structure into program instance
    def load_program_json(self, data):

        print("loading json program");

        if isinstance(data, str):  # if it is a string convert to JSON struct
            try:
                cfg = json.loads(data)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON: {e}")
        else:
            cfg = data

        self.name   = cfg.get("name", "")
        self.n      = cfg.get("n", 0)
        self.loaded = True

        instrs = []
        for entry in cfg.get("instruction_list", []):
            instr_dict = json.loads(entry) if isinstance(entry, str) else entry
            instr = Instruction.from_json(instr_dict)
            instrs.append(instr)

        self.instruction_list = instrs

        if self.n != len(instrs):
            raise ValueError(f"JSON corrupted n={self.n} is not number of instructions={len(instrs)}")
         
        self.variables    = [] # variable names (each appears only once, in program order)
        self.constants    = [] # constant values/variable names (only once, program order)
        self.loop_carried = [] # index to list of variable names which are loop-carried
        self.read_only    = [] # index to list of variable names which are read-only

        self.inst_dependence_list = []  ## list of instruction data dependencies
        # inst_dependence_list = [ i0, i1, i2 ... ]; 
        #       i0 = [ dep0, dep1, ...];   List of input dependencies, from 0 to 3
        #     dep0 = [ instID, varID / constID]; 
        #   instID = 0 to N-1  index of instruction generating input value
        #    varID = 0 to K-1  index of variable name representing input value
        #   instID = -1  means input value is constant
        #   instID = -3  means input value is read-only variable
        #  constID = 0 to C-1  index to constant name representing input constant

        Outs    = [] ## List of output variable names in program's instruction order
        Reads1  = [] ## List of  first input variable names in program's instruction order
        Reads2  = [] ## List of second input variable names in program's instruction order
        Reads3  = [] ## List of third output variable names in program's instruction order
        Consts  = [] ## List of constants in program's instruction order

        for inst in instrs:
            Outs.append  (inst.destin)
            Consts.append(inst.constant)
            Reads1.append(inst.source1)
            Reads2.append(inst.source2)
            Reads3.append(inst.source3)

        # List of variable names that are output of an instruction (appears only once)
        Outputs = list(set(Outs))  
        if "" in Outputs:
          Outputs.remove("")

        # List of variable names that are input of an instruction (appears only once)
        Inputs = list(set(Reads1+Reads2+Reads3))  
        if "" in Inputs:
          Inputs.remove("")

        # List of variable names (each appears only once, in program order)
        self.variables = list(set(Outputs+Inputs))
        if "" in self.variables:
          self.variables.remove("")

        # List of constant values / variable names (each appears only once)
        self.constants = list(set(Consts))
        if "" in self.constants:
          self.constants.remove("")
       
        # remove constants which are already a variable (this should not happen)
        setVars = set(self.variables)
        index = 0
        for c in self.constants:
          if c in setVars:
             self.constants.pop(index)
          else:
            index += 1

        # initialize list of producers for each variable as NONE
        producer_list = [-2 for _ in range(len(Outputs))]

        # analyze all instructions in program order to generate dependence info
        for inst_id in range(self.n):

            # create dependence list for intruction inst_id and append to program's dependence list
            dep_list = [] 
            self.inst_dependence_list.append(dep_list)

            const = Consts[inst_id]
            if const:  # register usage of this constant
                dep = [-1, self.constants.index(const)]
                dep_list.append(dep)

            source_var = Reads1[inst_id]
            if source_var:  # register dependence on this variable
                var_idx = self.variables.index(source_var)
                if source_var in Outputs:
                    out_idx  = Outputs.index(source_var)
                    prod_idx = producer_list[out_idx]
                else:  # read-only variable: acts as if it is a constant value
                    prod_idx = -3
                    self.read_only.append(source_var)
                dep = [prod_idx, var_idx]
                dep_list.append(dep)

            source_var = Reads2[inst_id]
            if source_var:  # register dependence on this variable
                var_idx = self.variables.index(source_var)
                if source_var in Outputs:
                    out_idx  = Outputs.index(source_var)
                    prod_idx = producer_list[out_idx]
                else:  # read-only variable: acts as if it is a constant value
                    prod_idx = -3
                    self.read_only.append(source_var)
                dep = [prod_idx, var_idx]
                dep_list.append(dep)

            source_var = Reads3[inst_id]
            if source_var:  # register dependence on this variable
                var_idx = self.variables.index(source_var)
                if source_var in Outputs:
                    out_idx  = Outputs.index(source_var)
                    prod_idx = producer_list[out_idx]
                else:  # read-only variable: acts as if it is a constant value
                    prod_idx = -3
                    self.read_only.append(source_var)
                dep = [prod_idx, var_idx]
                dep_list.append(dep)

            output_var = Outs[inst_id]
            if output_var:  # modify producer of this variable
                out_idx = Outputs.index(output_var)
                producer_list[out_idx] = inst_id

        # analyze all instructions in program order to solve loop-carried dependencies
        for inst_id in range(self.n):
            # obtain dependence list for intruction inst_id
            dep_list = self.inst_dependence_list[inst_id]
            for dep in dep_list:
                if dep[0] == -2: # dependence is pending to solve
                    source_var= self.variables[ dep[1] ]
                    out_idx   = Outputs.index(source_var)
                    prod_idx  = producer_list[out_idx]
                    dep[0] = prod_idx
                    self.loop_carried.append( (prod_idx, source_var) )

        # List of read-only variable names (each appears only once, in program order)
        self.read_only    = list(set(self.read_only))

        # List of tuples of loop-carried (producer, variable name) each appears only once
        self.loop_carried = list(set(self.loop_carried))

        self.generate_dependence_info()
        self.get_cyclic_paths()


    def generate_dependence_info (self):

        # Used by execution scheduler to control data dependencies during execution
        # For each static instruction, list of dependent offsets 
        # offset = positive number to subtract to my instruction ID to find dependent intr. ID

        self.dependence_edges = []  

        for inst_id in range(self.n):
            offsets = []
            for dep in self.inst_dependence_list[inst_id]:
                dep_id = dep[0]  # ID of instruction providing data to instruction inst_id
                if dep_id >= inst_id: # loop carried dependence
                    offset = inst_id - dep_id + self.n
                else:
                    offset = inst_id - dep_id
                offsets.append(offset)

            self.dependence_edges.append(offsets)


    def get_cyclic_paths(self):

        # return list of cyclic dependence paths: [[3, 3], [2, 0, 2]],
        # numbers are instr-IDs: same ID appears at begin & end

        start_instrs = []

        for inst_id in range(self.n):
            some_prev_dependence = False
            for dep in self.inst_dependence_list[inst_id]:
                if (dep[0] >= 0) and (dep[0] < inst_id):
                    some_prev_dependence = True
            if not some_prev_dependence:
                start_instrs.append(inst_id)

        # dependency graph in reverse order: from producer to consumer
        dependency_graph = {i:[] for i in range(self.n)}
        for inst_id in range(self.n):
            for dep in self.inst_dependence_list[inst_id]:
                if (dep[0] >= 0):
                    dependency_graph[dep[0]].append(inst_id)

        self.cyclic_paths = []
        paths             = [ [i]  for i in start_instrs]
        visited           = { i:[] for i in range(self.n)}

        while paths:
            path = paths.pop()
            last = path[-1]
            for dep_id in dependency_graph[last]:
                if dep_id not in visited[last]:
                    paths.append(path+[dep_id])
                    visited[last].append(dep_id)
                else:
                    if len(set(path)) != len(path):  # some inst_id appears twice
                        path = path[path.index(last):]
                        if path not in self.cyclic_paths:
                            self.cyclic_paths.append(path)


    def get_instr_latencies(self) -> list:

        # return list of latencies for ordered list of instructions

        latencies = []

        for i in range(self.n):
            resource = _processor.get_resource(self.instruction_list[i].type)
            if not resource:
                latency = 1
            else:
                latency = resource[0]
            latencies.append(latency)

        return latencies


    def get_instr_ports (self) -> list:

        # return list of port_usage masks for ordered list of instructions

        ports        = list( _processor.ports.keys() )
        n_ports      = len ( ports )
        resources    = []

        for i in range(self.n):
            resource   = _processor.get_resource(self.instruction_list[i].type)
            instr_mask = 0
            mask_bit   = 1
            for j in range(n_ports):
                if ports[j] in resource[1]:
                    instr_mask += mask_bit
                mask_bit *= 2
            resources.append(instr_mask)

        return resources


    def show_code(self) -> str:
        InsMessage = "INSTRUCTIONS"
        out = f"   {InsMessage:20}     TYPE      LATENCY  EXECUTION PORTS\n"
        for i in range(self.n):
            instruction = self.instruction_list[i]
            instr_type  = instruction.type
            resource    = _processor.get_resource(instr_type)
            if not resource:
                latency = 1
                ports = ()
            else:
                latency, ports = resource
            out += f"{i:{len(str(self.n))}}:"
            out += f"{instruction.text:20} : "
            out += f"{instr_type:18} : {latency:^3} : "

            n = len(ports)
            for j in range(n-1):
              out += f"P{ports[j]},"

            out += f"P{ports[n-1]}\n"
        return out



    def show_instruction_memory_trace(self) -> str:
        out = ""
        return out


    def show_memory_trace(self) -> str:
        out = "............................. Memory Trace Description ..........................."
        out += "\n...............................................................................\n\n"
        return out


    def show_graphviz(self, show_const=False,    show_readonly=False, 
                            show_internal=False, show_latency=False) -> str:

        colors = ["lightblue", "greenyellow", "lightyellow", 
                  "lightpink", "lightgrey",   "lightcyan", "lightcoral"]

        recurrent_paths = self.cyclic_paths
        latencies       = self.get_instr_latencies()

        max_latency    = 0   # maximum latency per iteration
        max_iters      = 0   # maximum number of iterations for cyclic path
        path_latencies = []  # latencies of cyclic paths

        for path in recurrent_paths:
            latency = sum( latencies[i] for i   in path[:-1] )
            iters   = sum( a >= b       for a,b in zip(path[:-1], path[1:]) )
            latency_iter = latency / iters
            path_latencies.append(latency_iter)
            if latency_iter > max_latency:
                max_latency = latency_iter
            max_iters = max( iters, max_iters )

        out  = "digraph G {\n  rankdir=\"TB\"; splines=spline; newrank=true;\n"
        out += "  edge [fontname=\"Consolas\"; color=black; penwidth=1.5; "
        out += "fontsize=14; fontcolor=blue];\n"

        # generate clusters of nodes: one cluster per loop iteration
        for iter_id in range(1, max_iters+1):
            out += f" subgraph cluster_{iter_id} "
            out +=  "{\n  style=\"filled,rounded\"; color=blue; "
            out += f"fillcolor={colors[iter_id-1]};\n"
            out +=  "  node [style=filled, shape=rectangle, fillcolor=lightgrey,"
            out +=  " fontname=\"Consolas\", fontsize=16, margin=0.0];\n"

            for inst_id in range(self.n):
                lat = latencies[inst_id]
                out += f"  i{iter_id}s{inst_id} ["
                if show_latency:
                  out += f"xlabel=<<B><font color=\"red\" point-size=\"16\">{lat}</font></B>>, "           
                out += f"label=< <B>{inst_id}: {self.instruction_list[inst_id].text}</B> >];\n"
            out +=  "}\n"

    
       # generate cluster of input variables
        out += " subgraph inVAR {\n"
        out += "  node[style=box,color=invis,width=0.5,heigth=0.5,fixedsize=true,fontname=\"Courier-bold\"];\n"

        for const_id in range( len(self.constants) ):
           var = self.constants[const_id]
           out += f"  Const{const_id} [label=\"{var}\", fontcolor=grey];\n"

        for RdOnly_id in range( len(self.read_only) ):
           var = self.read_only[RdOnly_id]
           out += f"  RdOnly{RdOnly_id} [label=\"{var}\", fontcolor=green];\n"

        for LoopCar_id in range( len(self.loop_carried) ):
           (_,var) = self.loop_carried[LoopCar_id]
           out += f"  LoopCar{LoopCar_id} [label=\"{var}\", fontcolor=red];\n"

        out += " }\n"

        out += " { rank=min; "
        for const_id in range( len(self.constants) ):
           out += f"Const{const_id}; "

        for RdOnly_id in range( len(self.read_only) ):
           out += f"RdOnly{RdOnly_id}; "

        for LoopCar_id in range( len(self.loop_carried) ):
           out += f"LoopCar{LoopCar_id}; "

        out += " }\n\n"


        # generate cluster of output variables
        out += " subgraph outVAR {\n"
        out += "  node [style=box, color=invis, fontcolor=red,"
        out += " width=0.5, heigth=0.5, fixedsize=true, fontname=\"Courier-bold\"];\n"

        for LoopCar_id in range( len(self.loop_carried) ):
           (_,var) = self.loop_carried[LoopCar_id]
           out += f"  OutCar{LoopCar_id} [label=\"{var}\"];\n"

        out += " }\n"

        out += " { rank=max; "
        for LoopCar_id in range( len(self.loop_carried) ):
           out += f"OutCar{LoopCar_id}; "

        out += " }\n\n"


        # generate dependence links: initial and intermediate
        for iter_id in range(1, max_iters+1):
          for inst_id in range(self.n):
            for dep in self.inst_dependence_list[inst_id]:

              i_id = dep[0]
              var  = dep[1]

              if i_id == -1:  # depends on Constant
                if show_const:
                  out += f"  Const{var} -> i{iter_id}s{inst_id}[color=grey];\n"
                else:
                  out += f"  Const{var} -> i{iter_id}s{inst_id}[color=invis];\n"
                continue

              if i_id == -3:  # depends on Read-Only variable
                label  = self.variables[var]
                RdOnly_id = self.read_only.index(label)
                if show_readonly:
                  out += f"  RdOnly{RdOnly_id} -> i{iter_id}s{inst_id}[color=green];\n"
                else:
                  out += f"  RdOnly{RdOnly_id} -> i{iter_id}s{inst_id}[color=invis];\n"
                continue

              # Check if current dependence is a part of a cyclical path
              is_recurrent = False
              for path in recurrent_paths:
                curr = path[0]
                next = path[1]
                if inst_id == next and i_id == curr :
                  is_recurrent = True
                  break
                else:
                  for i in range(len(path)-2):
                    curr = next
                    next = path[i+2]
                    if next == inst_id and curr == i_id:
                      is_recurrent = True
                      break

              if is_recurrent:
                  arrow = "color=red, penwidth=2.0"
              else:
                  arrow = ""

              if inst_id > i_id: ## Not loop-carried
                  in_var = f"i{iter_id}s{i_id}"
                  label  = self.variables[var]
              else:   ## Loop-carried
                  if iter_id == 1: # first loop iteration
                      var = self.variables[var]
                      for LoopCar_id in range( len(self.loop_carried) ):
                          (_,lc_var) = self.loop_carried[LoopCar_id]
                          if var == lc_var:
                             in_var = f"LoopCar{LoopCar_id}"
                             break
                      label  = ""
                  else:
                      in_var = f"i{iter_id-1}s{i_id}"
                      label  = self.variables[var]

              if not is_recurrent and not show_internal:
                  out += f"  {in_var} -> i{iter_id}s{inst_id} [color=invis];\n"
              else:
                  out += f"  {in_var} -> i{iter_id}s{inst_id} [label=\"{label}\", {arrow}];\n"


        # generate dependence links to loop-carried variables in final iteration
        for LoopCar_id in range( len(self.loop_carried) ):
           (prod_id,_) = self.loop_carried[LoopCar_id]

           # Check if current dependence is a part of a cyclical path
           is_recurrent = False
           for path in recurrent_paths:
             for i in range(len(path)-1):
               if prod_id == path[i]:
                 is_recurrent = True
                 break

           if is_recurrent:
               out += f"  i{max_iters}s{prod_id} -> OutCar{LoopCar_id}[color=red, penwidth=2.0];\n"
           else:
               out += f"  i{max_iters}s{prod_id} -> OutCar{LoopCar_id};\n"

        return out + "}\n"



    def show_performance_analysis(self) -> str:

        ports    = list( _processor.ports.keys() )
        n_ports  = len ( ports )

        recurrent_paths = self.cyclic_paths
        latencies       = self.get_instr_latencies()
        resources       = self.get_instr_ports()

        max_latency = 0
        for path in recurrent_paths:
            latency = sum(latencies[i] for i in path[:-1])
            iters   = sum(a >= b for a,b in zip(path[:-1], path[1:]))
            latency_iter = latency / iters
            if latency_iter > max_latency:
                max_latency = latency_iter

        dw_cycles = self.n / _processor.stages["dispatch"]
        rw_cycles = self.n / _processor.stages["retire"]

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


    def instr_str(self, i: int) -> str:
        return self.instruction_list[i].text
 

    def instr_type_str(self, i: int) -> str:
        return self.instruction_list[i].type


    def __repr__(self) -> str:
        out = ""
        for i in range(self.n):
            out += f"{i:{len(str(self.n))}}: {self.instruction_list[i]}\n"
        return out


    def __getitem__(self, i: int) -> Instruction:
        return self.instruction_list[i%self.n]


global _program = Program()
