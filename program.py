from .processor   import Processor, _processor
from .            import files
import json

global _program

class Instruction:

    def __init__(self) -> None:
        self.type     = ""
        self.text     = ""
        self.destin   = ""
        self.source1  = ""
        self.source2  = ""
        self.source3  = ""
        self.constant = ""


    def from_json(data: dict):

        instr = Instruction()
        instr.type     = data.get("type", "")
        instr.text     = data.get("text", "")
        instr.destin   = data.get("destin", "")
        instr.source1  = data.get("source1", "")
        instr.source2  = data.get("source2", "")
        instr.source3  = data.get("source3", "")
        instr.constant = data.get("constant", "")
        return instr


    def json(self) -> dict:
        return {
            "type":     self.type,
            "text":     self.text,
            "destin":   self.destin,
            "source1":  self.source1,
            "source2":  self.source2,
            "source3":  self.source3,
            "constant": self.constant
        }


    def __repr__(self) -> str:
        return f"{self.text: <16}"


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
    def json(self) -> str:
        return json.dumps(self.__dict__(), indent=2)


    # return JSON values of current program-class instance
    def __dict__(self) -> dict:
        data = {
            "name": self.name,
            "n":    self.n,
        }
        data["instruction_list"]=[]
        for instruction in self.instruction_list:
            data["instruction_list"].append(instruction.json())

        return data


    def __repr__(self) -> str:
        return json.dumps(self.__dict__(), indent=2)


    def __getitem__(self, i: int) -> Instruction:
        return self.instruction_list[i%self.n]


    def save(self, name="") -> None:
        if name == "":
            name = self.name
        files.export_json( self.json(), name, False)


    # Load JSON file containing program specification
    def load(self, file="") -> None:

        if file:
            json_name = f"{file}.json"
        else:
            json_name = "baseline.json"

        cfg = files.load_json ( json_name, False ) ## be sure is JSON struct

        if isinstance(cfg, str):  # if it is a string convert to JSON struct
            raise ValueError(f"Invalid JSON")

        self.name   = cfg.get("name", "")
        self.n      = cfg.get("n", 0)
        self.loaded = True

        instrs = []
        for entry in cfg.get("instruction_list", []):
            instr_dict = json.loads(entry) if isinstance(entry, str) else entry
            instr      = Instruction.from_json(instr_dict)
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


    def generate_dependence_info (self) -> None:

        # Used by execution scheduler to control data dependencies during execution
        # For each static instruction, list of dependent offsets 
        # offset = positive number to subtract to my instruction ID to find dependent intr. ID

        self.dependence_edges = []  

        for inst_id in range(self.n):
            offsets = []
            for dep in self.inst_dependence_list[inst_id]:
                dep_id = dep[0]  # ID of instruction providing data to instruction inst_id
                if dep_id >= 0:  # is a data dependence
                  if dep_id >= inst_id: # loop carried dependence
                    offset = inst_id - dep_id + self.n
                  else:
                    offset = inst_id - dep_id
                  offsets.append(offset)

            self.dependence_edges.append(offsets)


    def get_cyclic_paths(self) -> None:

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

        cyc_paths = []
        paths     = [ [i]  for i in start_instrs]
        visited   = { i:[] for i in range(self.n)}

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
                        if path not in cyc_paths:
                            cyc_paths.append(path)

        self.cyclic_paths = []
        for path in cyc_paths:
            path = path[:-1]      # remove last element (repeated as the first one)
            min_val   = min(path)            # find minimum value
            min_index = path.index(min_val)  # find position of minimum value
            path = path[min_index:]+path[:min_index+1]
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

        instr_pad, type_pad = 0, 0
        for i in range(self.n):
            instr_pad = max( instr_pad, len(self.instruction_list[i].text))
            type_pad  = max( type_pad,  len(self.instruction_list[i].type))

        InsMessage = "INSTRUCTIONS"
        TypeMessage= "TYPE"
        out = f"   {InsMessage:{instr_pad}}   {TypeMessage:{type_pad}} LATENCY EXECUTION PORTS\n"
        for i in range(self.n):
            instruction = self.instruction_list[i]
            instr_type  = instruction.type
            resource    = _processor.get_resource(instr_type)
            if not resource:
                latency = 1
                ports = ()
            else:
                latency, ports = resource
            out += f"{i:{len(str(self.n))}}: {instruction.text:{instr_pad}} : "
            out += f"{instr_type:{type_pad}} : {latency:^3} : "

            n = len(ports)
            for j in range(n-1):
              out += f"P{ports[j]},"

            out += f"P{ports[n-1]}\n"
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

        out  = "digraph G {\n  rankdir=\"LR\"; splines=spline; newrank=true;\n"
        out += "  edge [fontname=\"Consolas\"; color=black; penwidth=1.5; "
        out += "fontsize=14; fontcolor=blue];\n"

        # generate clusters of nodes: one cluster per loop iteration
        for iter_id in range(1, max_iters+1):
            out += f" subgraph cluster_{iter_id} "
            out +=  "{\n  style=\"filled,rounded\"; color=blue; "
            out += f"fillcolor={colors[iter_id-1]};\n"
            out +=  "  node [style=filled, shape=rectangle, fillcolor=lightgrey,"
            out +=  " margin=\"0.1,0.1\", fontname=\"Consolas\", fontsize=16, margin=0.05];\n"

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

        dw = _processor.stages["dispatch"]
        rw = _processor.stages["retire"]

        dw_cycles = self.n / dw
        rw_cycles = self.n / rw

        # generate all combinations of ports
        n_combinations = 1
        for i in range(n_ports):
            n_combinations *= 2

        port_cycles = 0
        for mask in range(1,n_combinations):
            uses = 0
            pw   = bin(mask).count("1")
            for instr_mask in resources:
                if (mask & instr_mask) == instr_mask:
                     uses += 1
            cycles = uses / pw
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
        if dw_cycles == max_cycles:
           out += f"dispatch stage: {self.n} instr. per iter. / {dw} instr. per cycle"
           out += f" = {dw_cycles:0.2f}\n"

        if rw_cycles == max_cycles:
           out += f" retire  stage: {self.n} instr. per iter. / {rw} instr. per cycle"
           out += f" = {rw_cycles:0.2f}\n"

        for mask in range(1,n_combinations):
            uses = 0
            inst_str= ""
            for i in range( len(resources) ):
                instr_mask = resources[i]
                if (mask & instr_mask) == instr_mask:  ## instruction only uses ports in mask
                     uses += 1
                     inst_str += f"{i},"

            pw   = bin(mask).count("1")
            cycles = uses / pw
            if cycles == max_cycles:
                port_str = ""
                mask_bit=1
                for j in range(n_ports):
                    if mask_bit & mask == mask_bit:
                        port_str += f"P{ports[j]}+"
                    mask_bit *= 2

                out += f"Ports: {port_str[:-1]}, Instr.: {inst_str[:-1]} --> {uses}"
                out += f" instr. per iter. / {pw} instr. per cycle = {cycles:0.2f}\n"

        out += f"\n*** Cyclic Dependence Paths:\n"
        for path in recurrent_paths:
            latency = sum(latencies[i] for i in path[:-1])
            iters   = sum(a >= b for a,b in zip(path[:-1], path[1:]))
            latency_iter = latency / iters

            out += " "
            for i in range( len(path)-1 ):
              cur_ins  = path[i]
              next_ins = path[i+1]
              for dep in self.inst_dependence_list[next_ins]:
                 if dep[0] == cur_ins:
                    var  = dep[1]
                    label= self.variables[var]

              out += f"[{cur_ins}] -({label})-> "

            out += f"[{path[-1]}] : "
            out += f"("
            if len(path)>2:
                for i in path[:-2]:
                  out += f"{latencies[i]}+"

            out += f"{latencies[path[-2]]})cycles / {iters} iter. = {latency_iter:0.2f}\n"

        return out


    def show_dependencies(self) -> str:

        out = "............... Instruction Data-Dependences ......................"
 
        for inst_id in range(self.n):
            instruction = self.instruction_list[inst_id]
            out += f"\n{inst_id:{len(str(self.n))}}: {instruction.text:20}: "

            for dep in self.inst_dependence_list[inst_id]:
                dep_id = dep[0]
                if dep_id == -1:  ## constant input
                  dep_var = self.constants[ dep[1] ]
                  out += f"\033[96m.. --> {dep_var:5};\033[0m "

                elif dep_id == -3:  ## read-only input variable
                  dep_var = self.variables[ dep[1] ]
                  out += f"\033[94m.. --> {dep_var:5};\033[0m "

                else:
                  dep_var = self.variables[dep[1]]
                  if dep_id >= inst_id:
                    out += f"\033[91m"
                  out += f"{dep_id:2} --> {dep_var:5}; "
                  if dep_id >= inst_id:
                    out += f"\033[0m"

        out += "\n\n Variables        : "
        for var in self.variables:
            out += f"{var},"
        out += "\n Constants        :\033[96m "
        for var in self.constants:
            out += f"{var},"
        out += "\n\033[0m Read-Only vars   :\033[94m "
        for var in self.read_only:
            out += f"{var},"
        out += "\n\033[0m Loop-Carried vars:\033[91m "
        for (prod_id, var) in self.loop_carried:
            out += f"{prod_id} --> {var},"

        out += "\033[0m\n..................................................................................\n"
        return out


_program = Program()
