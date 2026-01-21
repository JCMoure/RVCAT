from .processor import Processor, _processor
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
        self.inst_cyclic          = []  # list of inst_ids in cyclic paths (only once)


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


    # Load JSON object containing program specification
    def load(self, cfg) -> str:

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

        Insts = []
        for cyc_path in self.cyclic_paths:
          for iID in cyc_path:
            Insts.append  (iID)

        self.inst_cyclic = list(set(Insts))  
        # list of inst_ids in cyclic paths (only once)


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


    def get_critical_latencies (self, latencies):
        max_latency    = 0   # maximum latency per iteration
        min_iters      = 0   # minimum number of iterations for cyclic path
        path_latencies = []  # (latency,iters) of cyclic paths

        recurrent_paths = self.cyclic_paths
        for path in recurrent_paths:
            latency = sum( latencies[i] for i   in path[:-1] )
            iters   = sum( a >= b       for a,b in zip(path[:-1], path[1:]) )
            latency_iter = latency / iters
            path_latencies.append((latency, iters))
            if latency_iter > max_latency:
                max_latency = latency_iter
            min_iters = max( iters, min_iters )

        return (max_latency, min_iters, path_latencies)


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


    def show_graphviz(self, num_iters= 0,
                            show_internal=False, show_latency=False,
                            show_small   =False, show_full=   False 
                            ) -> str:

        def escape_html(text: str) -> str:
            """Escape HTML special characters for Graphviz HTML-like labels."""
            return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

        colors = ["lightblue", "greenyellow", "lightyellow", 
                  "lightpink", "lightgrey",   "lightcyan", "lightcoral"]

        recurrent_paths = self.cyclic_paths
        latencies       = self.get_instr_latencies()

        # max_latency    = maximum latency per iteration
        # min_iters      = minimum number of iterations for cyclic path
        # path_latencies = [ (latency,iters), (,) .. ]  of cyclic paths
        max_latency, min_iters, path_latencies = self.get_critical_latencies(latencies) 

        max_iters = max (min_iters, num_iters)

        out  = "digraph \"Data Dependence Graph\" {\n  rankdir=\"LR\"; splines=spline; newrank=true;\n"
        out += "  edge [fontname=\"courier\"; color=black; penwidth=1.5; fontcolor=blue];\n"

        # generate clusters of nodes: one cluster per loop iteration
        for iter_id in range(1, max_iters+1):
            out += f" subgraph cluster_{iter_id} "
            out +=  "{\n  style=\"filled,rounded\"; color=blue; "
            out += f"tooltip=\"Loop Iteration #{iter_id}\"; fillcolor={colors[iter_id-1]};\n"
            out +=  "  node [style=filled, shape=rect, fillcolor=lightgrey,"
            out +=  " margin=\"0.05,0\", fontname=\"courier\"];\n"

            for inst_id in range(self.n):
                if show_internal or (inst_id in self.inst_cyclic):
                  lat = latencies[inst_id]
                  txt = escape_html(self.instruction_list[inst_id].text)
                  out += f"  i{iter_id}s{inst_id} ["
                  out +=  "label=<<B>"
                  if show_latency:
                    out += f"<FONT COLOR=\"red\">({lat})</FONT> "
                  out += f"{inst_id}"
                  if show_small:
                    out += f"</B>>, tooltip=\"{txt}\"];\n"
                  else:
                    out += f": {txt}</B>>,tooltip=\"instruction\"];\n"

            out +=  "}\n"

    
        # generate cluster of input variables
        out += " subgraph inVAR {\n"
        out += "  node[style=box, color=invis, fixedsize=false, fontname=\"courier\"];\n"

        if show_full and show_internal:
          for const_id in range( len(self.constants) ):
             var = self.constants[const_id]
             out += f"  Const{const_id} [label=<<B>{var}</B>>, tooltip=\"constant\", fontcolor=grey];\n"

        if show_full and show_internal:
          for RdOnly_id in range( len(self.read_only) ):
             var = self.read_only[RdOnly_id]
             out += f"  RdOnly{RdOnly_id} [label=<<B>{var}</B>>, tooltip=\"read-only\", fontcolor=green];\n"

        for LoopCar_id in range( len(self.loop_carried) ):
           (inst_id,var) = self.loop_carried[LoopCar_id]
           cyclic = inst_id in self.inst_cyclic
           if show_internal or cyclic:
               out += f"  LoopCar{LoopCar_id} [label=<<B>{var}</B>>, tooltip=\"loop-recurrent\", "
               if cyclic:
                   out += "fontcolor=red];\n"
               else:
                   out += "fontcolor=blue];\n"

        out += " }\n"

        out += " { rank=min; "
                
        if show_full and show_internal:
          for const_id in range( len(self.constants) ):
             out += f"Const{const_id}; "

        if show_full and show_internal:
          for RdOnly_id in range( len(self.read_only) ):
             out += f"RdOnly{RdOnly_id}; "

        for LoopCar_id in range( len(self.loop_carried) ):
           (inst_id,_) = self.loop_carried[LoopCar_id]
           cyclic = inst_id in self.inst_cyclic
           if show_internal or cyclic:
             out += f"LoopCar{LoopCar_id}; "

        out += " }\n\n"


        # generate cluster of output variables
        out += " subgraph outVAR {\n"
        out += "  node [style=box, color=invis, fontcolor=red, fixedsize=false, fontname=\"courier\"];\n"

        for LoopCar_id in range( len(self.loop_carried) ):
           (inst_id,var) = self.loop_carried[LoopCar_id]
           cyclic = inst_id in self.inst_cyclic
           if show_internal or cyclic:
               out += f"  OutCar{LoopCar_id} "
               if cyclic:
                   out += f"[label=<<B>{var} : "
                   path = 0
                   while inst_id not in recurrent_paths[path]:
                       path = path+1
                   (lat,iters) = path_latencies[path]
                   if iters==1:
                     out += f"<FONT COLOR=\"blue\">{lat} cycles/iter</FONT></B>>"
                   else:
                     out += f"<FONT COLOR=\"blue\">{lat}/{iters}= {lat/iters} cycles/iter</FONT></B>>"
                   out += f", tooltip=\"cyclic path\"];\n"
               else:
                   out += f"[label=<<B>{var}</B>>, tooltip=\"not cyclic\", fontcolor=blue];\n"

        out += " }\n"

        out += " { rank=max; "
        for LoopCar_id in range( len(self.loop_carried) ):
           (inst_id,_) = self.loop_carried[LoopCar_id]
           cyclic = inst_id in self.inst_cyclic
           if show_internal or cyclic:
               out += f"OutCar{LoopCar_id}; "

        out += " }\n\n"


        # generate dependence links: initial and intermediate
        for iter_id in range(1, max_iters+1):
          for inst_id in range(self.n):
            for dep in self.inst_dependence_list[inst_id]:

              i_id = dep[0]
              var  = dep[1]

              if i_id == -1:  # inst_id depends on Constant
                if show_full and show_internal:
                  out += f"  Const{var} -> i{iter_id}s{inst_id}[color=grey,tooltip=\"depends on constant\"];\n"
                continue

              if i_id == -3:  # inst_id depends on Read-Only variable
                if show_full and show_internal:
                  label  = self.variables[var]
                  RdOnly_id = self.read_only.index(label)
                  out += f"  RdOnly{RdOnly_id} -> i{iter_id}s{inst_id}[color=green,tooltip=\"depends on read-only variable\"];\n"
                continue

              # inst_id depends on "normal" variable
              # Check if current dependence is a part of a cyclical path
              in_cyclic   = inst_id in self.inst_cyclic
              out_cyclic  = i_id    in self.inst_cyclic 
              is_recurrent= in_cyclic and out_cyclic

              if is_recurrent:
                  arrow = "color=red, penwidth=2.0"
              else:
                  arrow = ""

              if inst_id > i_id: ## Not loop-carried
                  in_var = f"i{iter_id}s{i_id}"
                  if show_small:
                    label = ""
                  else:
                    label = self.variables[var]
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
                      if show_small:
                          label = ""
                      else:
                          label  = self.variables[var]

              if is_recurrent:
                  out += f"  {in_var} -> i{iter_id}s{inst_id} [label=\"{label}\","
                  out += f" labeltooltip=\"dependence variable: {label}\","
                  out += f" tooltip=\"dependence on cyclical path\", {arrow}];\n"
              elif show_internal:
                  out += f"  {in_var} -> i{iter_id}s{inst_id} [label=\"{label}\","
                  out += f" labeltooltip=\"dependence variable: {label}\","
                  out += f" tooltip=\"not on cyclical path\", {arrow}];\n"

        # generate dependence links to loop-carried variables in final iteration
        for LoopCar_id in range( len(self.loop_carried) ):
           (prod_id,_) = self.loop_carried[LoopCar_id]
           cyclic      = prod_id in self.inst_cyclic
           if cyclic:
               out += f"  i{max_iters}s{prod_id} -> OutCar{LoopCar_id}[color=red, penwidth=2.0,tooltip=\"cyclic output dependence\"];\n"
           elif show_internal:
               out += f"  i{max_iters}s{prod_id} -> OutCar{LoopCar_id}[color=blue, penwidth=2.0, tooltip=\"non-cyclic output dependence\"];\n"

        return out + "}\n"


    def get_performance_analysis(self) -> dict:

        analysis = { "name": self.name }

        ports    = list( _processor.ports.keys() )
        n_ports  = len ( ports )

        recurrent_paths = self.cyclic_paths
        latencies       = self.get_instr_latencies()
        resources       = self.get_instr_ports()

        # max_latency    = maximum latency per iteration
        # min_iters      = minimum number of iterations for cyclic path
        # path_latencies = [ (latency,iters), (,) .. ]  of cyclic paths
        max_latency, min_iters, path_latencies = self.get_critical_latencies(latencies) 

        dw = _processor.dispatch
        rw = _processor.retire

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

        analysis["LatencyTime"]=    max_latency 
        analysis["ThroughputTime"]= max_cycles

        cycles_limit = max_cycles
        if (max_latency > max_cycles):
            analysis["performance-bound"] = "LATENCY"
            cycles_limit = max_latency
        elif (max_latency < max_cycles):
            analysis["performance-bound"] = "THROUGHPUT"
        else:
            analysis["performance-bound"] = "LATENCY+THROUGHPUT"
        
        analysis["BestTime"] = cycles_limit
        analysis["Throughput-Bottlenecks"] = []

        if dw_cycles == max_cycles:
           text = f"Dispatch: {self.n} instr. per iter. / {dw} instr. per cycle = {dw_cycles:0.2f}"
           analysis["Throughput-Bottlenecks"].append(text)

        if rw_cycles == max_cycles:
           text = f"Retire: {self.n} instr. per iter. / {rw} instr. per cycle = {rw_cycles:0.2f}"
           analysis["Throughput-Bottlenecks"].append(text)

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

                text = f"Ports: {port_str[:-1]}, Instr.: {inst_str[:-1]} -->"
                text+= f"{uses} instr. per iter. / {pw} instr. per cycle = {cycles:0.2f}"
                analysis["Throughput-Bottlenecks"].append(text)

        return json.dumps(analysis, indent=2)


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
        print("Recurrent Paths: ", self.cyclic_paths)
        print("Cyclic Insts:    ", self.inst_cyclic)
        print("Dependence List: ", self.inst_dependence_list)

        return out

_program = Program()
