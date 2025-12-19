from math import inf

def old_priority(isps):
      _ais    = [inf]               # assigned instructions
      _aps    = [-1]                # assigned ports
      nis     = len(isps)           # number of instructions
      isps_is = sorted(isps.keys()) # instructions indexes

      def dfs(n=0, ais=[], aps=[]):
          if n == nis:
                nonlocal _ais, _aps
                if len(ais) >= len(_ais) and sum(ais) < sum(_ais):
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
      return dict(zip(_ais, _aps))


def generate_execution_graph (program, N, window_size, DepEdges):

   ExecGraph = []
   static_instructions = program.n
        
   # First Node contains a fake arch on dispatch node and retire node, 
   # that will be removed after inserting values
   for i in range(0,N):  # each dynamic instruction executed, except first one

      # Insert node corresponding to dispatch stage of current instruction
      DispatchEdges = [ [(i-1)*3 , 0] ]   # Dispatch node depends on dispatch of previous instruction
      if i >= window_size :  # Dependence on Retire node corresponding to finite ROB (Window) size
           DispatchEdges.append( [(i-window_size)*3+2 , 0] )
      ExecGraph.append( DispatchEdges)   # Add Dispatch node

      # Insert node corresponding to execution stage of current instruction
      ExecuteEdges = [ [i*3, 1] ]  # depends on dispatch of current instruction, with latency = 1
      for dep_offsets in DepEdges[ i % static_instructions]:
           j = i - dep_offsets
           if j >= 0:  # dependence on dynamic instruction
               ExecuteEdges.append( [j*3+1, 0] )  # depends on execution stage of prev. instr. (latency annotated later)
      ExecGraph.append( ExecuteEdges )  # Add Execution node

      # Insert node corresponding to retire stage of current instruction
      RetireEdges = [ [i*3+1, 1] ]  # depends on execution stage of current instr., lat=1 + measured execution latency (later)
      RetireEdges.append([(i-1)*3+2, 0])  # depends on retire of previous instruction
      ExecGraph.append( RetireEdges )     # Add Retire node

   return ExecGraph


def get_iteration_idx( program, index ):
     instr_idx = index // 3
     static_idx= instr_idx  % program.n
     iteration = instr_idx // program.n
     return iteration, static_idx


def get_node_arch ( program, index, cost ):
     iteration, idx = get_iteration_idx(program, index)
     name = f" --({cost})--> [{iteration},{idx}]"
     if     index%3 == 0:
         name += "Disp"
     elif   index%3 == 1:
         name += "eXec"
     else:
         name += "Retr"
     return name


def longest_path (ExecGraph):
      N = len(ExecGraph)
      dist = [-10**9 for i in range(N)]  # initialize distances to all vertices as infinite
      path = [  []   for i in range(N)]  # initialize longest path to all vertices as EMPTY

      dist[N-1] = 0
      path[N-1] = [[N-1, 1]]
      for u in range(N-1,0,-1):
          for node in ExecGraph[u]:
              if dist[node[0]] < dist[u] + node[1]:
                    dist[node[0]] = dist[u] + node[1]
                    new_path      = path[u] + [node]
                    path[node[0]] = new_path

      return path[0]


def get_list_of_edges (list):
     str = ""
     for node in list:
         str += get_node_arch(node[0], node[1]) + " ; " 
     return str


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


def critical_path_statistics (program, path):
     N         = program.n
     total_lat = 0
     histogram = [0 for i in range(N)]
     decode_lat= 0
     retire_lat= 0
        
     for node in path:
         stage = node[0] % 3
         iteration, idx = get_iteration_idx(program, node[0])
         if stage == 1:
             histogram[idx] += node[1]
         elif stage == 0:
             decode_lat += node[1]
         else:
             retire_lat += node[1]
         total_lat += node[1]

     out = ""
     for i in range(N):
         out += f"    Instr. {i:2}: {100*histogram[i]/total_lat:0.2f}%\n"

     out += f"    DISPATCH : {100*decode_lat/total_lat:0.2f}%\n"
     out += f"    RETIRE   : {100*retire_lat/total_lat:0.2f}%\n"
     return out


def critical_path_statistics_json (program, path):
    N         = program.n
    total_lat = 0
    histogram = [0 for i in range(N)]
    decode_lat= 0
    retire_lat= 0

    for node in path:
         stage = node[0] % 3
         iteration, idx = get_iteration_idx(program, node[0])
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
                                    'instruction': program.instruction_list[i].text,
                                    'percentage': 100*histogram[i]/total_lat})

    out['dispatch'] = 100*decode_lat/total_lat
    out['retire']   = 100*retire_lat/total_lat

    return out


def print_graph ( program, ExecGraph ):
     n_times_3 = len( ExecGraph )
     n         = n_times_3 // 3
     for i in range(n):
         static_idx= i % program.n
         iteration = i // program.n
         out  = f"[{iteration},{static_idx}]:\n"
         out += f"   Dispatch= {get_list_of_edges(ExecGraph[i*3])}\n"
         out += f"   Execute = {get_list_of_edges(ExecGraph[i*3+1])}\n"
         out += f"   Retire  = {get_list_of_edges(ExecGraph[i*3+2])}\n"
     print(out)


def exec_graph_update(ExecGraph, dynamic_idx, disp_latency, exec_latency, ret_latency):

     # IMPORTANT: in execution graph, dispatch and retire latencies are set to a maximum of 1 cycle
     #   since we do not want this to be an explanation of performance
     if disp_latency > 1:
         disp_latency = 1
     if ret_latency > 1:
         ret_latency = 1

     ExecGraph[dynamic_idx*3+0][0][1]  = disp_latency  # update dispatch latency on node

     for dep_node in ExecGraph[dynamic_idx*3+1][1:]:   # update execution latencies of dependent instructions
        dep_node[1] = ExecGraph[dep_node[0]+1][0][1] - 1

     ExecGraph[dynamic_idx*3+2][0][1] += exec_latency  # update execution latency of retire node
     ExecGraph[dynamic_idx*3+2][1][1]  = ret_latency   # update retire latency on node

     if dynamic_idx == 0:
        ExecGraph[0].pop(-1)  # remove last arch from first dispatch node
        ExecGraph[2].pop(-1)  # remove last arch from first retire node

