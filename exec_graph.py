from array import array


class CompactExecutionGraph:

    __slots__ = ("offsets", "dependencies", "weights")

    def __init__(self):
        self.offsets = array("I", [0])
        self.dependencies = array("I")
        self.weights = array("q")

    def __len__(self):
        return len(self.offsets) - 1

    def append_node(self, edges):
        for dependency, weight in edges:
            self.dependencies.append(dependency)
            self.weights.append(weight)
        self.offsets.append(len(self.dependencies))

    def iter_edges(self, node):
        start = self.offsets[node]
        end = self.offsets[node + 1]
        for edge in range(start, end):
            yield self.dependencies[edge], self.weights[edge]

    def to_list(self):
        return [
            [[dependency, weight] for dependency, weight in self.iter_edges(node)]
            for node in range(len(self))
        ]


def old_priority(isps):
      # Optimal port assignment of one cycle: isps = {window index: [ports it can use]}.
      # Each instruction uses its port for one cycle, so the best assignment of each cycle is
      # the one that issues the most instructions; among those, the oldest ones (smallest
      # window indexes). Returns {window index: port}.
      _ais    = None                # assigned instructions of the best assignment
      _aps    = None                # assigned ports
      nis     = len(isps)           # number of instructions
      isps_is = sorted(isps.keys()) # instructions indexes

      def dfs(n=0, ais=[], aps=[]):
          if n == nis:
                nonlocal _ais, _aps
                # first more instructions, then older ones (a larger assignment is better
                # even if the sum of its indexes is larger)
                if _ais is None or len(ais) > len(_ais) or \
                   (len(ais) == len(_ais) and sum(ais) < sum(_ais)):
                    _ais = ais
                    _aps = aps
                return

          i = isps_is[n]
          assigned = False
          for p in isps[i]:
                if p not in aps:
                    assigned = True
                    dfs(n+1, ais+[i], aps+[p])

          if not assigned:
                dfs(n+1, ais, aps)

      dfs()
      return dict(zip(_ais or [], _aps or []))

def generate_execution_graph (static_instructions, N, window_size, DepEdges):

   ExecGraph = CompactExecutionGraph()
        
   for i in range(0,N):  # each dynamic instruction executed, except first one

      DispatchEdges = []
      if i > 0:
           DispatchEdges.append(((i-1)*3, 0))
      if i >= window_size :  # Dependence on Retire node corresponding to finite ROB (Window) size
           DispatchEdges.append(((i-window_size)*3+2, 0))
      ExecGraph.append_node(DispatchEdges)

      ExecuteEdges = [(i*3, 1)]
      for dep_offsets in DepEdges[ i % static_instructions]:
           j = i - dep_offsets
           if j >= 0:  # dependence on dynamic instruction
               ExecuteEdges.append((j*3+1, 0))
      ExecGraph.append_node(ExecuteEdges)

      RetireEdges = [(i*3+1, 1)]
      if i > 0:
           RetireEdges.append(((i-1)*3+2, 0))
      ExecGraph.append_node(RetireEdges)

   return ExecGraph

def build_rows_graph(rows, window_size):
    # Execution graph of a simulation with conditional branches, built after it from the rows
    # (dispatched instructions, in dispatch order). rows: [{"correct", "deps" (row indices of
    # the producers), "disp", "exec", "ret"}]. Correct-path rows get the same nodes and weights
    # as generate_execution_graph + exec_graph_update; wrong-path rows get nodes without edges.
    ExecGraph = CompactExecutionGraph()
    previous = None
    correct_rows = []
    for r, row in enumerate(rows):
        if not row["correct"]:
            for _ in range(3):
                ExecGraph.append_node([])
            continue
        disp = min(row["disp"], 1)
        ret  = min(row["ret"], 1)
        dispatch_edges = []
        if previous is not None:
            dispatch_edges.append((previous * 3, disp))
        if len(correct_rows) >= window_size:
            dispatch_edges.append((correct_rows[-window_size] * 3 + 2, 0))
        ExecGraph.append_node(dispatch_edges)
        ExecGraph.append_node([(r * 3, 1)] + [(d * 3 + 1, rows[d]["exec"]) for d in row["deps"]])
        retire_edges = [(r * 3 + 1, 1 + row["exec"])]
        if previous is not None:
            retire_edges.append((previous * 3 + 2, ret))
        ExecGraph.append_node(retire_edges)
        correct_rows.append(r)
        previous = r
    return ExecGraph

def get_iteration_idx( n, index ):
     instr_idx = index // 3
     static_idx= instr_idx  % n
     iteration = instr_idx // n
     return iteration, static_idx

def longest_path (ExecGraph):
      node_count = len(ExecGraph)
      dist = [-10**9 for _ in range(node_count)]
      next_node = [-1 for _ in range(node_count)]
      path_weight = [0 for _ in range(node_count)]

      sink = node_count - 1
      dist[sink] = 0
      if isinstance(ExecGraph, CompactExecutionGraph):
          for node in range(sink, 0, -1):
              for edge in range(ExecGraph.offsets[node], ExecGraph.offsets[node + 1]):
                  dependency = ExecGraph.dependencies[edge]
                  weight = ExecGraph.weights[edge]
                  if dist[dependency] < dist[node] + weight:
                        dist[dependency] = dist[node] + weight
                        next_node[dependency] = node
                        path_weight[dependency] = weight
      else:
          for node in range(sink, 0, -1):
              for dependency, weight in ExecGraph[node]:
                  if dist[dependency] < dist[node] + weight:
                        dist[dependency] = dist[node] + weight
                        next_node[dependency] = node
                        path_weight[dependency] = weight

      path = []
      node = 0
      while node != sink and next_node[node] != -1:
          path.append([node, path_weight[node]])
          node = next_node[node]

      if node != sink:
          return []

      path.append([sink, 1])
      path.reverse()
      return path

def serialize_execution_graph(ExecGraph, dynamic_instruction_count):
    node_count = len(ExecGraph)
    return {
        "version": 1,
        "dynamic_instruction_count": int(dynamic_instruction_count),
        "node_count": node_count,
        "source": 0,
        "sink": node_count - 1,
        "stages": ["dispatch", "execute", "retire"],
        "dependencies_by_node": [
            [[int(dependency), int(weight)] for dependency, weight in
             (ExecGraph.iter_edges(node) if isinstance(ExecGraph, CompactExecutionGraph) else ExecGraph[node])]
            for node in range(node_count)
        ]
    }

def find_repeating_critical_path_pattern(N, instr_list, path, iterations, locate=None):
    if N < 1 or iterations < 1 or not path:
        return None

    signatures = [[] for _ in range(iterations)]
    for node, weight in reversed(path):
        if locate is None:
            iteration, static_idx = (node // 3) // N, (node // 3) % N
        else:
            iteration, static_idx = locate(node)
        if iteration < iterations:
            signatures[iteration].append(
                (static_idx, node % 3, int(weight))
            )

    best_start = 0
    best_end = 0
    start = 0
    while start < iterations:
        signature = signatures[start]
        if not signature:
            start += 1
            continue
        end = start + 1
        while end < iterations and signatures[end] == signature:
            end += 1
        if end - start > best_end - best_start:
            best_start, best_end = start, end
        start = end

    if best_end - best_start < 2:
        return None

    signature = signatures[best_start]
    return {
        "start_iteration": best_start + 1,
        "end_iteration": best_end,
        "repetitions": best_end - best_start,
        "cycles_per_iteration": sum(weight for _, _, weight in signature),
        "prefix_iterations": best_start,
        "suffix_iterations": iterations - best_end,
        "nodes": [
            {
                "instruction_index": instruction_idx,
                "instruction": instr_list[instruction_idx].text,
                "stage": ("dispatch", "execute", "retire")[stage],
                "cycles": weight
            }
            for instruction_idx, stage, weight in signature
        ]
    }


def critical_path_statistics_json (N, instr_list, path, iterations=None, locate=None):
    # locate(node) -> (iteration, static index); by default node // 3 is iteration * N + index
    total_lat = 0
    histogram = [0 for i in range(N)]
    decode_lat= 0
    retire_lat= 0

    for node in path:
         stage = node[0] % 3
         iteration, idx = get_iteration_idx(N, node[0]) if locate is None else locate(node[0])
         if stage == 1:
             histogram[idx] += node[1]
         elif stage == 0:
             decode_lat += node[1]
         else:
             retire_lat += node[1]
         total_lat += node[1]

    out = {'instructions': []}
    for i in range(N):
        out['instructions'].append({'id': i,
                                    'instruction': instr_list[i].text,
                                    'percentage': 100*histogram[i]/total_lat})

    out['dispatch'] = 100*decode_lat/total_lat
    out['retire']   = 100*retire_lat/total_lat

    if iterations is None:
        iterations = max((node[0] // 3) // N for node in path) + 1
    repeating_pattern = find_repeating_critical_path_pattern(
        N, instr_list, path, iterations, locate
    )
    if repeating_pattern is not None:
        out["repeating_pattern"] = repeating_pattern

    return out

def exec_graph_update(ExecGraph, dynamic_idx, disp_latency, exec_latency, ret_latency):

     # IMPORTANT: in execution graph, dispatch and retire latencies are set to a maximum of 1 cycle
     #   since we do not want this to be an explanation of performance
     if disp_latency > 1:
         disp_latency = 1
     if ret_latency > 1:
         ret_latency = 1

     dispatch_node = dynamic_idx*3
     execute_node = dispatch_node + 1
     retire_node = dispatch_node + 2

     if isinstance(ExecGraph, CompactExecutionGraph):
        dispatch_edge = ExecGraph.offsets[dispatch_node]
        if dynamic_idx > 0:
            ExecGraph.weights[dispatch_edge] = disp_latency

        for edge in range(ExecGraph.offsets[execute_node] + 1, ExecGraph.offsets[execute_node + 1]):
            dependency = ExecGraph.dependencies[edge]
            dependency_dispatch_edge = ExecGraph.offsets[dependency + 1]
            ExecGraph.weights[edge] = ExecGraph.weights[dependency_dispatch_edge] - 1

        retire_edge = ExecGraph.offsets[retire_node]
        ExecGraph.weights[retire_edge] += exec_latency
        if dynamic_idx > 0:
            ExecGraph.weights[retire_edge + 1] = ret_latency
        return

     ExecGraph[dispatch_node][0][1] = disp_latency

     for dep_node in ExecGraph[execute_node][1:]:
        dep_node[1] = ExecGraph[dep_node[0]+1][0][1] - 1

     ExecGraph[retire_node][0][1] += exec_latency
     ExecGraph[retire_node][1][1] = ret_latency

     if dynamic_idx == 0:
        ExecGraph[0].pop(-1)
        ExecGraph[2].pop(-1)

# NOT USED, but useful for debugging
def get_node_arch ( n, index, cost ):
     iteration, idx = get_iteration_idx(n, index)
     name = f" --({cost})--> [{iteration},{idx}]"
     if     index%3 == 0:
         name += "Disp"
     elif   index%3 == 1:
         name += "eXec"
     else:
         name += "Retr"
     return name

# NOT USED, but useful for debugging
def print_graph ( n, ExecGraph ):
    if isinstance(ExecGraph, CompactExecutionGraph):
        ExecGraph = ExecGraph.to_list()

    def get_list_of_edges (list):
        str = ""
        for node in list:
            str += get_node_arch(node[0], node[1]) + " ; " 
        return str 
    
    n_times_3 = len( ExecGraph )
    N         = n_times_3 // 3
    for i in range(N):
        static_idx= i % n
        iteration = i // n
        out  = f"[{iteration},{static_idx}]:\n"
        out += f"   Dispatch= {get_list_of_edges(ExecGraph[i*3])}\n"
        out += f"   Execute = {get_list_of_edges(ExecGraph[i*3+1])}\n"
        out += f"   Retire  = {get_list_of_edges(ExecGraph[i*3+2])}\n"
    print(out)

# NOT USED, but useful for debugging
def print_path (path):
     path_str = f"CRITICAL Path:\n      "
     count = 5
     for node in path:
         path_str += get_node_arch(node[0], node[1]) + " "
         count -= 1
         if count == 0:
             count = 5
             path_str += "\n      "

     print(path_str+"\n")