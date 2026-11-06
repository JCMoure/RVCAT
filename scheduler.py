from .window   import Window, InstrState
from .program  import Process, _program
from .cache    import Cache
from .         import exec_graph as ex
import json
import random

global _scheduler

class Scheduler:

    def __init__(self) -> None:
        self.iterations = 0
        self.window_size= 1
        self.dispWidth  = 1
        self.retrWidth  = 1
        self.sched      = "optimal"
        self.nBlocks    = 1
        self.blkSize    = 1
        self.mPenalty   = 0
        self.mIssueTime = 0
        self.nFillBuffers = 2
        self.nWriteBuffers = 2
        self.rThru = 1
        self.port_mask  = 0
        self.n_ports    = 0
        self.cache      = None
        self.window     = Window(1)
        self.num_instr  = 0
        self.n          = 0
        self.dispatched = 0
        self.pc         = 0
        self.cycles     = 0
        self.DepEdges   = []
        self.dynamic    = False   # program with conditional branches: dynamic dispatch (see below)

    def next_cycle(self) -> int:

        xw    = self.n_ports
        rw    = self.retrWidth
        sched = self.sched != "greedy"

        issue_queue = {}
        resolved    = []   # mispredicted branches that finish their execution in this cycle
        used_ports  = {port:False for port in range(32) if (self.port_mask >> port) & 1}
        ReadMisses  = []
        SecondMisses= []
        WriteMisses = []
        MMupdates   = []
        if self.cache is not None:
            MMupdates.extend(self.cache.advance(self.cycles))

        for window_idx in range(self.window.count):

            instr       = self.window[window_idx]
            static_idx  = instr.s_idx
            dynamic_idx = instr.d_idx
            instr.waiting_for = None
            instr.waiting_ports = []

            if instr.state == InstrState.WRITE_BACK:
                if rw:
                    if window_idx == 0 or self.window[window_idx-1].state == InstrState.RETIRE:
                        instr.state    = InstrState.RETIRE
                        instr.substate = InstrState.NONE
                        rw -= 1
                    else:
                        instr.substate = InstrState.WAIT_RETIRE
                else:
                    instr.substate = InstrState.WAIT_RETIRE

            elif instr.state == InstrState.LOAD or instr.state == InstrState.STORE:
                if self.cache is None:
                    instr.latency -= 1
                    if instr.latency <= 0:
                        instr.state = InstrState.WRITE_BACK
                        instr.substate = InstrState.NONE
                        if instr.wrong:
                            kind = "reads" if instr.memory == 1 else "writes"
                            self.wp[kind] += 1
                elif instr.substate in (
                    InstrState.WAIT_MM_REQUEST,
                    InstrState.WAIT_MM_READY,
                    InstrState.WAIT_DATA_READY,
                    InstrState.WAIT_CACHE_2ND,
                    InstrState.WAIT_RETURN_QUEUE,
                ):
                    request_state = self.cache.get_request_state(dynamic_idx)
                    if request_state == "returned":
                        self.cache.consume_completion(dynamic_idx)
                        instr.state = InstrState.WRITE_BACK
                        instr.substate = InstrState.NONE
                    elif request_state == "return_queue":
                        instr.substate = InstrState.WAIT_RETURN_QUEUE
                        instr.exec_lat += 1
                    elif request_state in (
                        "queued_fill",
                        "queued_line",
                        "queued_write",
                        "waiting_mm",
                    ):
                        instr.substate = InstrState.WAIT_MM_REQUEST
                        instr.exec_lat += 1
                    elif request_state == "waiting_writeback":
                        instr.substate = InstrState.WAIT_MM_READY
                        instr.exec_lat += 1
                    else:
                        instr.substate = InstrState.WAIT_DATA_READY
                        instr.exec_lat += 1
                else:
                    instr.latency -= 1
                    if instr.latency <= 0:
                        access = instr.memory - 1
                        if instr.wrong and instr.memory == 2:
                            access = 2   # wrong-path store: requests the block (RFO), never writes it
                        result = self.cache.request_access(
                            access,
                            instr.memAddr,
                            self.cycles,
                            dynamic_idx,
                        )
                        if instr.wrong:
                            kind = "reads" if instr.memory == 1 else "writes"
                            self.wp[kind] += 1
                            if result != "hit":
                                self.wp[kind[:-1] + "_misses"] += 1
                        if result == "hit":
                            instr.state = InstrState.WRITE_BACK
                            instr.substate = InstrState.NONE
                        else:
                            if instr.memory == 1:
                                ReadMisses.append(dynamic_idx)
                            else:
                                WriteMisses.append(dynamic_idx)
                            if result in ("merged", "secondary"):
                                SecondMisses.append(dynamic_idx)
                            instr.substate = (
                                InstrState.WAIT_CACHE_2ND
                                if result == "secondary"
                                else InstrState.WAIT_MM_REQUEST
                            )

            elif instr.state == InstrState.EXECUTE:
                instr.latency -= 1
                if instr.latency == 0:
                    instr.state    = InstrState.WRITE_BACK
                    instr.substate = InstrState.NONE
                    if instr.mispredicted:
                        resolved.append(instr)

            elif instr.state == InstrState.DISPATCH:
                if instr.substate in [InstrState.NONE, InstrState.WAIT_DATA]:
                    instr.substate = InstrState.NONE
                    instr.waiting_for = []
                  
                    if self.dynamic:   # producers found by renaming at dispatch
                        for dep_idx in instr.deps:
                            instr_dep = self.window.find(dep_idx)
                            if instr_dep and instr_dep.state not in [InstrState.WRITE_BACK, InstrState.RETIRE]:
                                instr.substate = InstrState.WAIT_DATA
                                if instr_dep.d_idx not in instr.waiting_for:
                                    instr.waiting_for.append(instr_dep.d_idx)
                    else:
                      for dependence_offset in self.DepEdges[static_idx]:
                        instr_dep = self.window.get_instr( dynamic_idx - dependence_offset )
                        if not instr_dep: # instruction is no longer in the window
                            continue
                        else:
                            if instr_dep.state not in [InstrState.WRITE_BACK, InstrState.RETIRE]:
                                instr.substate = InstrState.WAIT_DATA
                                if instr_dep.d_idx not in instr.waiting_for:
                                    instr.waiting_for.append(instr_dep.d_idx)

                if instr.substate != InstrState.WAIT_DATA:
                    port_mask = _program.instruction_list[static_idx].ports
                    latency   = _program.instruction_list[static_idx].latency
                    required_ports= [port for port in range(32) if (port_mask >> port) & 1]
                    if not sched:  # Greedy scheduling algorithm
                      if xw:
                        for port in required_ports:
                            if not used_ports[port]:
                                used_ports[port] = True
                                instr.exec_cycle = self.cycles
                                instr.latency    = latency
                                instr.exec_lat  += latency
                                if instr.memory > 0:
                                    instr.state = InstrState.LOAD if instr.memory == 1 else InstrState.STORE
                                else:
                                    instr.state = InstrState.EXECUTE
                                instr.substate   = InstrState.NONE
                                instr.port_used  = port
                                instr.port_uses.append((self.cycles, port))
                                xw -= 1
                                break
                        if instr.state == InstrState.DISPATCH:
                            instr.substate  = InstrState.WAIT_RESOURCE
                            instr.waiting_ports = [
                                port for port in required_ports if used_ports[port]
                            ] or required_ports
                            instr.exec_lat += 1
                      else:
                        instr.substate  = InstrState.WAIT_BANDWIDTH
                        instr.exec_lat += 1

                    else:   # Optimal scheduling: first priority is age, second is using most ports
                      issue_queue[window_idx] = required_ports
                      instr.latency           = latency

            elif instr.state != InstrState.RETIRE:
                print("ERROR")


        if sched:  # Improved scheduling algorithm
            issd_isps = ex.old_priority(issue_queue)
            for w_idx in issue_queue:
                instr          = self.window[w_idx]
                instr.substate = InstrState.NONE
                if xw:
                    if w_idx in issd_isps:
                        port             = issd_isps[w_idx]
                        instr.port_used  = port
                        instr.port_uses.append((self.cycles, port))
                        used_ports[port] = True
                        instr.exec_cycle = self.cycles
                        if instr.memory > 0:
                            instr.state = InstrState.LOAD if instr.memory == 1 else InstrState.STORE
                        else:
                            instr.state = InstrState.EXECUTE
                        instr.exec_lat += instr.latency
                        xw -= 1
                    else:
                        instr.substate = InstrState.WAIT_RESOURCE
                        instr.waiting_ports = [
                            port for port in issue_queue[w_idx] if used_ports[port]
                        ] or issue_queue[w_idx]
                        instr.exec_lat += 1
                else:
                    instr.substate = InstrState.WAIT_BANDWIDTH
                    instr.exec_lat += 1

        for branch in resolved:
            self._resolve(branch)

        if self.cache is not None:
            MMupdates.extend(self.cache.advance(self.cycles))

        retires = self.retrWidth - rw
        return retires, used_ports, ReadMisses, SecondMisses, WriteMisses, MMupdates

    def dispatch(self):
        if self.dynamic:
            return self._dispatch_dynamic()
        dw = self.dispWidth
        while self.dispatched < self.n and dw and not self.window.is_full():
            static_idx = self.pc % self.num_instr
            instr_mem  = 0
            addr       = -1
            instr      = _program[static_idx]
            if instr.type == "MEM" or instr.type == "VMEM":
                instr_mem  = 1 if instr.oper == "LOAD" else 2
                addr       = instr.addr
                instr.addr = addr + instr.byte_stride
    
            self.window.push(self.cycles, self.pc, static_idx, instr_mem, addr)
            self.pc += 1
            dw      -= 1
            self.dispatched +=1

        self.cycles += 1

    def generate_timeline_state ( self, dynamic_idx, stages, critical_path):
        
        criticalList = []

        # Decode Stage
        decode_stage = "D"
        stages.pop(0)

        if len(critical_path) > 0:
          node = critical_path[-1]
          idx  = node[0] // 3
          stage= node[0] % 3
          if idx == dynamic_idx and stage == 0:
            if node[1] == 1:
                criticalList.append(0)  # Decode stage is in critical path
            critical_path.pop(-1)

        cycle = 1
        while stages[0] == InstrState.WAIT_DATA:
            decode_stage += stages[0].value
            stages.pop(0)
            cycle = cycle+1
        
        # Execute Stage
        execute_stage = ""
        count = 0

        if len(critical_path) > 0:
          node = critical_path[-1]
          idx  = node[0] // 3
          stage= node[0] % 3
          if idx == dynamic_idx and stage == 1:
            count = node[1]-1
            criticalList.append(cycle)  # Execute stage is in critical path
            critical_path.pop(-1)
        
        while stages[0] != InstrState.RETIRE:
            execute_stage += stages[0].value
            stages.pop(0)
            cycle = cycle+1
            if count > 0:
                count = count-1
                criticalList.append(cycle)  # Execute stage is in critical path
        
        # Retire Stage
        retire_stage = "R"
        if len(critical_path) > 0:
          node = critical_path[-1]
          idx  = node[0] // 3
          stage= node[0] % 3
          if idx == dynamic_idx and stage == 2:
              critical_path.pop(-1)
              if node[1] == 1:
                criticalList.append(cycle)  # Execute stage is in critical path

        return (decode_stage + execute_stage + retire_stage, criticalList)

    def generate_timeline(self, ports):
        rw              = self.retrWidth
        retired         = 0
        self.dispatched = 0
        self.cycles     = 0
        last_ret_cycle  = 0
        last_disp_cycle = 0

        timeline      = {i:[] for i in range(self.n + self.window.size + rw)}
        port_timeline = {port:[] for port in ports}
        cache_states = []
        self.fill_buffer_snapshots = []
        self.write_buffer_snapshots = []
        last_cache_state = None
        INSTR_Info    = []
        self.wait_details = []

        ExecGraph     = ex.generate_execution_graph( self.num_instr, self.n, self.window_size, self.DepEdges )

        while retired < self.n:
            retires, used_ports, _,_,_,_ = self.next_cycle()

            if self.cache is not None:
                cache_cycle = self.cycles
                cache_state = self.cache.get_state(cache_cycle)
                cache_signature = tuple(
                    (line["valid"], line["address"], line["dirty"], line["lru"],
                     line["ready_cycle"], line["loading"])
                    for line in cache_state
                )
                if cache_signature != last_cache_state:
                    cache_states.append({
                        "cycle": cache_cycle,
                        "lines": cache_state,
                    })
                    last_cache_state = cache_signature
                buffer_state = self.cache.get_buffer_state()
                self.fill_buffer_snapshots.append({
                    "cycle": cache_cycle,
                    "slots": buffer_state["fill"],
                })
                self.write_buffer_snapshots.append({
                    "cycle": cache_cycle,
                    "slots": buffer_state["write"],
                })

            for port, used in used_ports.items():
                port_timeline[port].append(used)

            for i in range(retires):
                r_instr     = self.window[i]
                dynamic_idx = r_instr.d_idx
                if dynamic_idx != retired:
                    print("ERROR\n")

                disp_latency    = r_instr.disp_cycle - last_disp_cycle
                last_disp_cycle = r_instr.disp_cycle
                ret_latency     = self.cycles - last_ret_cycle
                last_ret_cycle  = self.cycles
                exec_latency    = r_instr.exec_lat

                INSTR_Info.append([
                    r_instr.exec_cycle,
                    r_instr.port_used,
                    r_instr.memAddr,
                    r_instr.port_uses,
                ])

                timeline[ dynamic_idx ].append((self.cycles, r_instr.state))

                ex.exec_graph_update ( ExecGraph, dynamic_idx, disp_latency, exec_latency, ret_latency ) 

                retired += 1
                if retired >= self.n:
                    break

            self.window.pop(retires)
            self.dispatch()

            for instr in self.window:
                if instr.substate != InstrState.NONE:
                    timeline[instr.d_idx].append((self.cycles, instr.substate))
                    if instr.substate == InstrState.WAIT_DATA:
                        self.wait_details.append({
                            "cycle": self.cycles - 1,
                            "instruction_index": instr.d_idx,
                            "reason": "data",
                            "dependencies": instr.waiting_for,
                        })
                    elif instr.substate == InstrState.WAIT_RESOURCE:
                        self.wait_details.append({
                            "cycle": self.cycles - 1,
                            "instruction_index": instr.d_idx,
                            "reason": "ports",
                            "ports": instr.waiting_ports,
                        })
                    elif instr.substate == InstrState.WAIT_BANDWIDTH:
                        self.wait_details.append({
                            "cycle": self.cycles - 1,
                            "instruction_index": instr.d_idx,
                            "reason": "issue-bandwidth",
                        })
                    elif instr.state in (InstrState.LOAD, InstrState.STORE) and \
                            instr.substate in (
                                InstrState.WAIT_MM_REQUEST,
                                InstrState.WAIT_MM_READY,
                                InstrState.WAIT_DATA_READY,
                                InstrState.WAIT_CACHE_2ND,
                            ):
                        self.wait_details.append({
                            "cycle": self.cycles - 1,
                            "instruction_index": instr.d_idx,
                            "reason": "cache",
                            "block_address": (
                                instr.memAddr // self.blkSize
                            ) * self.blkSize,
                            "buffer_state": self.cache.get_request_state(instr.d_idx),
                        })
                    elif instr.substate == InstrState.WAIT_RETURN_QUEUE:
                        self.wait_details.append({
                            "cycle": self.cycles - 1,
                            "instruction_index": instr.d_idx,
                            "reason": "cache-return",
                            "block_address": (
                                instr.memAddr // self.blkSize
                            ) * self.blkSize,
                        })
                else:
                    timeline[instr.d_idx].append((self.cycles, instr.state))

        critical_path = ex.longest_path(ExecGraph)

        return timeline, port_timeline, INSTR_Info, critical_path, ExecGraph, cache_states

    def get_timeline(self, processJSON, niters: int = 3, nret=None) -> str:

        if nret is not None and (isinstance(nret, bool) or not isinstance(nret, int) or nret < 1):
            raise ValueError("nret must be a positive integer.")

        process = Process.from_json(processJSON)
        _program.load_instruction_list(process.instruction_list)

        self.iterations = niters
        self.window_size= process.ROBsize
        self.window     = Window(process.ROBsize)
        self.DepEdges   = _program.dependence_edges
        self.dispWidth  = process.dispatch
        self.retrWidth  = process.retire
        self.mPenalty   = process.mPenalty
        self.mIssueTime = process.mIssueTime
        self.nFillBuffers = process.nFillBuffers
        self.nWriteBuffers = process.nWriteBuffers
        self.rThru = process.rThru
        self.sched      = process.sched
        self.blkSize    = process.blkSize
        self.nBlocks    = process.nBlocks

        _program.assign_memory_addresses(process.Nloop)
        self._setup_dynamic(process)
        
        # Always creat a new cache object to reset cache state, even if nBlocks is 0 (no cache)
        if self.nBlocks > 0:
            self.cache  = Cache(
                self.nBlocks, self.blkSize, self.mPenalty, self.mIssueTime,
                record_requests=True,
                fill_buffer_count=self.nFillBuffers,
                write_buffer_count=self.nWriteBuffers,
                return_throughput=self.rThru,
            )
        else:
            self.cache = None
            
        self.num_instr  = _program.n
        self.n          = nret if nret is not None else niters*self.num_instr
        self.pc         = 0
        self.cycles     = 0
        self.dispatched = 0

        all_ports = 0
        for instr in _program.instruction_list:
            all_ports |= instr.ports
        self.port_mask = all_ports

        # list of used ports and number of used ports
        ports        = [i for i in range(32) if (all_ports >> i) & 1]
        self.n_ports = len(ports)

        if self.dynamic:
            return self._timeline_dynamic(ports, nret)

        timeline, port_timeline, INSTR_Info, critical_path, ExecGraph, cache_states = self.generate_timeline(ports)

        instructions = []    # List of timeline.instructions

        for i, cycles in timeline.items():

            if not cycles or i >= self.n:
                break

            stages, criticalList = self.generate_timeline_state( i, [s for _,s in cycles], critical_path)

            instr = [
                i // self.num_instr,   # loop iteration
                i % self.num_instr,    # instruction Index
                cycles[0][0]-1,        # starting cycle
                INSTR_Info[i][1],      # port
                stages,                # states
                criticalList,          # critical states
                INSTR_Info[i][2]       # memory address
            ]
            instructions.append(instr)   # insert new instruction in timeline structure

        timelineJson                 = {}
        timelineJson["cycles"]       = self.cycles
        timelineJson["instructions"] = instructions
        timelineJson["arrays"]       = _program.arrays
        timelineJson["critical_path_graph"] = ex.serialize_execution_graph(ExecGraph, self.n)
        timelineJson["wait_details"] = self.wait_details
        timelineJson["resource_usage"] = {
            "ports": port_timeline,
            "port_owners": {
                str(port): [[] for _ in range(self.cycles)]
                for port in ports
            },
        }
        for instruction_index, info in enumerate(INSTR_Info):
            for cycle, port in info[3]:
                timelineJson["resource_usage"]["port_owners"][str(port)][cycle].append(
                    instruction_index
                )
        if self.cache is not None:
            mm_usage = [False] * self.cycles
            for request in self.cache.MEM_requests:
                request_start = request["cycle"]
                for cycle in range(request_start, request_start + self.mIssueTime):
                    if 0 <= cycle < self.cycles:
                        mm_usage[cycle] = True
            timelineJson["resource_usage"]["mm"] = mm_usage
            timelineJson["resource_usage"]["mm_requests"] = self.cache.MEM_requests
            timelineJson["resource_usage"]["cache_state"] = {
                "line_count": self.cache.CACHE_SIZE,
                "snapshots": cache_states,
            }
            timelineJson["resource_usage"]["fill_buffers"] = {
                "capacity": self.cache.FILL_BUFFER_COUNT,
                "snapshots": self.fill_buffer_snapshots,
            }
            timelineJson["resource_usage"]["write_buffers"] = {
                "capacity": self.cache.WRITE_BUFFER_COUNT,
                "snapshots": self.write_buffer_snapshots,
            }

        return json.dumps(timelineJson)

    def get_results(self, processJSON, niters: int = 3) -> str:

        process = Process.from_json(processJSON)
        _program.load_instruction_list(process.instruction_list)

        self.iterations = niters
        self.window_size= process.ROBsize
        self.window     = Window(process.ROBsize)
        self.DepEdges   = _program.dependence_edges
        self.dispWidth  = process.dispatch
        self.retrWidth  = process.retire
        self.mPenalty   = process.mPenalty
        self.mIssueTime = process.mIssueTime
        self.nFillBuffers = process.nFillBuffers
        self.nWriteBuffers = process.nWriteBuffers
        self.rThru = process.rThru
        self.sched      = process.sched
        self.blkSize    = process.blkSize
        self.nBlocks    = process.nBlocks

        _program.assign_memory_addresses(process.Nloop)
        self._setup_dynamic(process)
        
        if self.nBlocks > 0:
            self.cache  = Cache(
                self.nBlocks,
                self.blkSize,
                self.mPenalty,
                self.mIssueTime,
                record_requests=True,
                fill_buffer_count=self.nFillBuffers,
                write_buffer_count=self.nWriteBuffers,
                return_throughput=self.rThru,
            )
        else:
            self.cache = None

        self.num_instr  = _program.n
        self.n          = niters*self.num_instr
        self.pc         = 0
        self.cycles     = 0
        self.dispatched = 0

        retired         = 0
        last_ret_cycle  = 0
        last_disp_cycle = 0
        Reads, Writes = 0, 0
        RdMisses, WrMisses, S2Misses = 0, 0, 0
        RdPrimaryMisses, RdSecondaryMisses = 0, 0
        WrPrimaryMisses, WrSecondaryMisses = 0, 0

        all_ports = 0
        for instr in _program.instruction_list:
            all_ports |= instr.ports
        self.port_mask = all_ports

        # list of used ports and number of used ports
        ports        = [i for i in range(32) if (all_ports >> i) & 1]
        self.n_ports = len(ports)
        port_usage   = {port:0 for port in ports}

        if self.dynamic:
            return self._results_dynamic(ports)

        ExecGraph  = ex.generate_execution_graph( self.num_instr, self.n, self.window_size, self.DepEdges )

        while retired < self.n:
            retires, used_ports, ReadMisses, SecondMisses, WriteMisses, MMupdates = self.next_cycle()
            secondary_misses = set(SecondMisses)

            for idx in ReadMisses:
                if idx < self.n:
                    RdMisses += 1
                    if idx in secondary_misses:
                        RdSecondaryMisses += 1
                    else:
                        RdPrimaryMisses += 1

            for idx in WriteMisses:
                if idx < self.n:
                    WrMisses += 1
                    if idx in secondary_misses:
                        WrSecondaryMisses += 1
                    else:
                        WrPrimaryMisses += 1

            for idx in SecondMisses:
                if idx < self.n:
                    S2Misses += 1

            for port in ports:
                if used_ports[port]:
                   port_usage[port] += 1

            for i in range(retires):
                r_instr     = self.window[i]
                dynamic_idx = r_instr.d_idx
                if dynamic_idx != retired:
                    print("ERROR\n")

                disp_latency    = r_instr.disp_cycle - last_disp_cycle
                last_disp_cycle = r_instr.disp_cycle
                ret_latency     = self.cycles - last_ret_cycle
                last_ret_cycle  = self.cycles
                exec_latency    = r_instr.exec_lat
                ex.exec_graph_update ( ExecGraph, dynamic_idx, disp_latency, exec_latency, ret_latency )

                if r_instr.memory != 0:  # LOAD or STORE
                    if r_instr.memory == 1:  # LOAD
                        Reads += 1
                    elif r_instr.memory == 2:  # STORE
                        Writes += 1

                retired += 1
                if retired >= self.n:
                    break

            self.window.pop(retires)
            self.dispatch()

        critical_path   = ex.longest_path(ExecGraph)
        cycles_per_iter = self.cycles / self.iterations
        IPC             = self.n      / self.cycles

        out = {}
        out["total_iterations"]     = self.iterations
        out["total_instructions"]   = self.n
        out["total_cycles"]         = self.cycles
        out["ipc"]                  = IPC
        out["cycles_per_iteration"] = cycles_per_iter
        out["ports"] = {}
        for port in ports:
           usage = port_usage[port]/self.cycles
           out["ports"][str(port)] = usage*100

        mm_requests = self.cache.MEM_requests if self.cache is not None else []
        mm_reads = sum(request["operation"] != "write" for request in mm_requests)
        mm_writes = sum(request["operation"] == "write" for request in mm_requests)
        mm_busy_cycles = {
            cycle
            for request in mm_requests
            for cycle in range(request["cycle"], request["cycle"] + request["duration"])
            if 0 <= cycle < self.cycles
        }

        out["reads"]          = Reads
        out["read_misses"]    = RdMisses
        out["read_primary_misses"] = RdPrimaryMisses
        out["read_secondary_misses"] = RdSecondaryMisses
        out["writes"]         = Writes
        out["write_misses"]   = WrMisses
        out["write_primary_misses"] = WrPrimaryMisses
        out["write_secondary_misses"] = WrSecondaryMisses
        out["second_misses"]  = S2Misses
        out["MM_Reads"]       = mm_reads
        out["MM_Writes"]      = mm_writes
        out["MM_usage_percent"] = 100 * len(mm_busy_cycles) / self.cycles

        out["critical_path"]   = ex.critical_path_statistics_json(
            self.num_instr, _program.instruction_list, critical_path, self.iterations
        )
        return json.dumps(out)

    # ==============================================================================================
    # Programs with conditional branches ("if c skip k" inside the loop body)
    #   - the dynamic instruction stream depends on the outcome of each branch, generated with a
    #     fixed seed from its probability of being taken (reproducible);
    #   - a branch is mispredicted with its given rate, or else by a 2-bit saturating counter;
    #   - producers are found by renaming at dispatch (table variable -> last producer);
    #   - memory addresses are computed from the iteration of each instruction;
    #   - after a misprediction, the simulation option "speculation" chooses:
    #       stall:      dispatch stops until the branch resolves, plus bPenalty cycles;
    #       wrong-path: dispatch follows the wrong path (its later branches follow their actual
    #                   direction, without nested mispredictions) until the branch resolves or
    #                   the ROB is full; then the wrong-path instructions are squashed (their
    #                   cache accesses in flight finish), and dispatch resumes after bPenalty.
    # ==============================================================================================
    def _setup_dynamic(self, process):
        branches = _program.conditional_branches()
        self.dynamic = bool(branches)
        if not self.dynamic:
            return
        self.skips        = dict(branches)
        self.speculation  = process.speculation
        self.bPenalty     = process.bPenalty
        self.sources      = [_program.read_variables(i) for i in range(_program.n)]
        self.addr0        = [inst.addr for inst in _program.instruction_list]
        self.rename       = {}
        self.cursor       = (0, 0)
        self.wrong_cursor = None
        self.blocked_by   = None
        self.stall_until  = 0
        self.dispatch_done= False
        self.next_d       = 0
        self.rows         = []
        self.last_squashed= []
        self.outcomes     = {b: [] for b in self.skips}
        self.rngs         = {b: random.Random(1000 + 7919 * b) for b in self.skips}
        self.mrngs        = {b: random.Random(5000 + 104729 * b) for b in self.skips}
        self.counters     = {b: 1 for b in self.skips}
        self.mispredictions = 0
        self.branches_executed = 0
        self.wp = {"dispatched": 0, "executed": 0, "squashed": 0,
                   "reads": 0, "read_misses": 0, "writes": 0, "write_misses": 0}

    def _outcome(self, b, k):
        # outcome (taken) of conditional branch b in iteration k
        seq = self.outcomes[b]
        while len(seq) <= k:
            seq.append(self.rngs[b].random() < _program.instruction_list[b].prob)
        return seq[k]

    def _mispredicted(self, b, taken):
        rate = _program.instruction_list[b].mispredict
        if rate is not None:
            return self.mrngs[b].random() < rate
        counter = self.counters[b]                  # 2-bit saturating counter
        self.counters[b] = min(3, counter + 1) if taken else max(0, counter - 1)
        return (counter >= 2) != taken

    def _dispatch_dynamic(self):
        dw = self.dispWidth
        while dw and not self.window.is_full():
            if self.cycles < self.stall_until or self.blocked_by is not None:
                break
            wrong = self.wrong_cursor is not None
            if wrong:
                k, s = self.wrong_cursor
                if k >= self.iterations:          # the wrong path leaves the loop
                    break
            else:
                if self.dispatch_done:
                    break
                k, s = self.cursor
            instr = _program[s]
            mem, addr = 0, -1
            if instr.type == "MEM" or instr.type == "VMEM":
                mem  = 1 if instr.oper == "LOAD" else 2
                addr = self.addr0[s] + k * instr.byte_stride
            d = self.next_d
            self.next_d += 1
            self.window.push(self.cycles, d, s, mem, addr)
            inst = self.window.last_pushed()
            inst.iteration = k
            inst.wrong     = wrong
            inst.deps      = [self.rename[v] for v in self.sources[s] if v in self.rename]
            self.rows.append(inst)
            if wrong:
                self.wp["dispatched"] += 1
            if instr.destin:
                self.rename[instr.destin] = d
            dw -= 1

            if s in self.skips:
                taken  = self._outcome(s, k)
                target = (k, s + 1 + self.skips[s])
                actual = target if taken else (k, s + 1)
                if not wrong:
                    self.branches_executed += 1
                    if self._mispredicted(s, taken):
                        inst.mispredicted = True
                        inst.checkpoint   = dict(self.rename)
                        self.mispredictions += 1
                        self.cursor = actual
                        if self.speculation == "wrong-path":
                            self.wrong_cursor = (k, s + 1) if taken else target
                        else:
                            self.blocked_by = d
                        continue
                nxt = actual
            elif s == self.num_instr - 1:      # final branch of the loop
                nxt = (k + 1, 0)
                if not wrong and k == self.iterations - 1:
                    self.dispatch_done = True
            else:
                nxt = (k, s + 1)
            if wrong:
                self.wrong_cursor = nxt
            else:
                self.cursor = nxt

        self.cycles += 1

    def _resolve(self, branch):
        # a mispredicted branch finishes: squash the wrong path, restore renaming, refill the front-end
        removed = self.window.truncate_after(branch.d_idx)
        for r in removed:
            r.squashed_cycle = self.cycles
            if r.state != InstrState.DISPATCH:
                self.wp["executed"] += 1
            if self.cache is not None:
                self.cache.cancel(r.d_idx)
        self.wp["squashed"] += len(removed)
        self.last_squashed.extend(removed)
        if branch.checkpoint is not None:
            self.rename = branch.checkpoint
        self.wrong_cursor = None
        self.blocked_by   = None
        self.stall_until  = self.cycles + self.bPenalty

    def _branch_statistics(self):
        return {
            "speculation": self.speculation,
            "penalty": self.bPenalty,
            "branches": self.branches_executed,
            "mispredictions": self.mispredictions,
            "mispredictions_per_iteration": self.mispredictions / self.iterations,
            "wrong_path_dispatched": self.wp["dispatched"],
            "wrong_path_executed": self.wp["executed"],
            "wrong_path_reads": self.wp["reads"],
            "wrong_path_read_misses": self.wp["read_misses"],
            "wrong_path_writes": self.wp["writes"],
            "wrong_path_write_misses": self.wp["write_misses"],
        }

    def _graph_rows(self, rows):
        # rows (dispatched instructions, in order) -> input of ex.build_rows_graph
        position = {r.d_idx: i for i, r in enumerate(rows)}
        return [{"correct": not r.wrong,
                 "deps": [position[d] for d in (r.deps or []) if d in position],
                 "disp": getattr(r, "disp_lat", 0), "exec": r.exec_lat, "ret": getattr(r, "ret_lat", 0)}
                for r in rows]

    def _results_dynamic(self, ports):
        port_usage = {port: 0 for port in ports}
        retired = []
        last_ret_cycle = last_disp_cycle = 0
        Reads = Writes = 0
        RdMisses = WrMisses = S2Misses = 0
        RdPrimaryMisses = RdSecondaryMisses = WrPrimaryMisses = WrSecondaryMisses = 0
        wrong_ids = lambda idx: self.rows[idx].wrong if idx < len(self.rows) else False

        while not (self.dispatch_done and self.window.count == 0):
            retires, used_ports, ReadMisses, SecondMisses, WriteMisses, MMupdates = self.next_cycle()
            secondary = set(SecondMisses)
            for idx in ReadMisses:
                if not wrong_ids(idx):
                    RdMisses += 1
                    if idx in secondary: RdSecondaryMisses += 1
                    else:                RdPrimaryMisses += 1
            for idx in WriteMisses:
                if not wrong_ids(idx):
                    WrMisses += 1
                    if idx in secondary: WrSecondaryMisses += 1
                    else:                WrPrimaryMisses += 1
            for idx in SecondMisses:
                if not wrong_ids(idx):
                    S2Misses += 1
            for port in ports:
                if used_ports[port]:
                    port_usage[port] += 1
            for i in range(retires):
                r = self.window[i]
                r.disp_lat = r.disp_cycle - last_disp_cycle
                last_disp_cycle = r.disp_cycle
                r.ret_lat = self.cycles - last_ret_cycle
                last_ret_cycle = self.cycles
                retired.append(r)
                if r.memory == 1:   Reads += 1
                elif r.memory == 2: Writes += 1
            self.last_squashed = []
            self.window.pop(retires)
            self.dispatch()
            if self.cycles > 10**7:
                raise RuntimeError("simulation does not finish")

        rows = self._graph_rows(retired)
        ExecGraph = ex.build_rows_graph(rows, self.window_size)
        critical_path = ex.longest_path(ExecGraph)
        locate = lambda node: (retired[node // 3].iteration, retired[node // 3].s_idx)

        n = len(retired)
        out = {}
        out["total_iterations"]     = self.iterations
        out["total_instructions"]   = n
        out["total_cycles"]         = self.cycles
        out["ipc"]                  = n / self.cycles
        out["cycles_per_iteration"] = self.cycles / self.iterations
        out["ports"] = {str(port): 100 * port_usage[port] / self.cycles for port in ports}
        mm_requests = self.cache.MEM_requests if self.cache is not None else []
        mm_busy_cycles = {
            cycle for request in mm_requests
            for cycle in range(request["cycle"], request["cycle"] + request["duration"])
            if 0 <= cycle < self.cycles
        }
        out["reads"]          = Reads
        out["read_misses"]    = RdMisses
        out["read_primary_misses"] = RdPrimaryMisses
        out["read_secondary_misses"] = RdSecondaryMisses
        out["writes"]         = Writes
        out["write_misses"]   = WrMisses
        out["write_primary_misses"] = WrPrimaryMisses
        out["write_secondary_misses"] = WrSecondaryMisses
        out["second_misses"]  = S2Misses
        out["MM_Reads"]       = sum(request["operation"] != "write" for request in mm_requests)
        out["MM_Writes"]      = sum(request["operation"] == "write" for request in mm_requests)
        out["MM_usage_percent"] = 100 * len(mm_busy_cycles) / self.cycles
        out["branch"]         = self._branch_statistics()
        out["critical_path"]  = ex.critical_path_statistics_json(
            self.num_instr, _program.instruction_list, critical_path, self.iterations, locate
        ) if critical_path else {"instructions": [], "dispatch": 0, "retire": 0}
        return json.dumps(out)

    def _timeline_dynamic(self, ports, nret):
        # the timeline is limited by retired instructions (nret), not by iterations: each iteration
        # retires at least one instruction, so nret iterations are always enough
        if nret is not None:
            self.iterations = max(self.iterations, nret)
        states        = {}
        port_timeline = {port: [] for port in ports}
        cache_states  = []
        self.fill_buffer_snapshots = []
        self.write_buffer_snapshots = []
        self.wait_details = []
        last_cache_state = None
        retired = 0
        last_retired_d = -1
        last_ret_cycle = last_disp_cycle = 0

        def record(instr):
            states.setdefault(instr.d_idx, [])
            if instr.substate != InstrState.NONE:
                states[instr.d_idx].append((self.cycles, instr.substate))
                reason = {InstrState.WAIT_DATA: "data", InstrState.WAIT_RESOURCE: "ports",
                          InstrState.WAIT_BANDWIDTH: "issue-bandwidth"}.get(instr.substate)
                if reason == "data":
                    self.wait_details.append({"cycle": self.cycles - 1, "instruction_index": instr.d_idx,
                                              "reason": reason, "dependencies": instr.waiting_for})
                elif reason == "ports":
                    self.wait_details.append({"cycle": self.cycles - 1, "instruction_index": instr.d_idx,
                                              "reason": reason, "ports": instr.waiting_ports})
                elif reason is not None:
                    self.wait_details.append({"cycle": self.cycles - 1, "instruction_index": instr.d_idx,
                                              "reason": reason})
                elif instr.state in (InstrState.LOAD, InstrState.STORE) and self.cache is not None:
                    self.wait_details.append({
                        "cycle": self.cycles - 1, "instruction_index": instr.d_idx,
                        "reason": "cache-return" if instr.substate == InstrState.WAIT_RETURN_QUEUE else "cache",
                        "block_address": (instr.memAddr // self.blkSize) * self.blkSize})
            else:
                states[instr.d_idx].append((self.cycles, instr.state))

        while not (self.dispatch_done and self.window.count == 0) and (nret is None or retired < nret):
            retires, used_ports, _, _, _, _ = self.next_cycle()
            if self.cache is not None:
                cache_state = self.cache.get_state(self.cycles)
                signature = tuple((line["valid"], line["address"], line["dirty"], line["lru"],
                                   line["ready_cycle"], line["loading"]) for line in cache_state)
                if signature != last_cache_state:
                    cache_states.append({"cycle": self.cycles, "lines": cache_state})
                    last_cache_state = signature
                buffer_state = self.cache.get_buffer_state()
                self.fill_buffer_snapshots.append({"cycle": self.cycles, "slots": buffer_state["fill"]})
                self.write_buffer_snapshots.append({"cycle": self.cycles, "slots": buffer_state["write"]})
            for port, used in used_ports.items():
                port_timeline[port].append(used)
            for i in range(retires):
                r = self.window[i]
                r.disp_lat = r.disp_cycle - last_disp_cycle
                last_disp_cycle = r.disp_cycle
                r.ret_lat = self.cycles - last_ret_cycle
                last_ret_cycle = self.cycles
                states.setdefault(r.d_idx, []).append((self.cycles, r.state))
                last_retired_d = r.d_idx
                retired += 1
                if nret is not None and retired >= nret:
                    break
            for r in self.last_squashed:
                states.setdefault(r.d_idx, []).append((self.cycles, InstrState.SQUASHED))
            self.last_squashed = []
            self.window.pop(retires)
            self.dispatch()
            for instr in self.window:
                record(instr)
            if self.cycles > 10**6:
                raise RuntimeError("simulation does not finish")

        rows = self.rows[:last_retired_d + 1]
        ExecGraph = ex.build_rows_graph(self._graph_rows(rows), self.window_size)
        critical_path = ex.longest_path(ExecGraph)

        instructions = []
        for i, r in enumerate(rows):
            cycles = states.get(r.d_idx, [])
            if not cycles:
                continue
            seq = [st for _, st in cycles]
            if r.wrong:
                text = "D" + "".join(st.value for st in seq[1:] if st != InstrState.SQUASHED) + "x"
                critical = []
            else:
                text, critical = self.generate_timeline_state(i, seq, critical_path)
            instructions.append([r.iteration, r.s_idx, cycles[0][0] - 1, r.port_used, text, critical,
                                 r.memAddr, {"wrong": r.wrong, "mispredicted": r.mispredicted}])

        timelineJson = {
            "cycles": self.cycles,
            "instructions": instructions,
            "arrays": _program.arrays,
            "critical_path_graph": ex.serialize_execution_graph(ExecGraph, len(rows)),
            "wait_details": self.wait_details,
            "branch": self._branch_statistics(),
            "resource_usage": {
                "ports": port_timeline,
                "port_owners": {str(port): [[] for _ in range(self.cycles)] for port in ports},
            },
        }
        for index, r in enumerate(rows):
            for cycle, port in r.port_uses:
                if cycle < self.cycles:
                    timelineJson["resource_usage"]["port_owners"][str(port)][cycle].append(index)
        if self.cache is not None:
            mm_usage = [False] * self.cycles
            for request in self.cache.MEM_requests:
                for cycle in range(request["cycle"], request["cycle"] + self.mIssueTime):
                    if 0 <= cycle < self.cycles:
                        mm_usage[cycle] = True
            timelineJson["resource_usage"]["mm"] = mm_usage
            timelineJson["resource_usage"]["mm_requests"] = self.cache.MEM_requests
            timelineJson["resource_usage"]["cache_state"] = {"line_count": self.cache.CACHE_SIZE,
                                                             "snapshots": cache_states}
            timelineJson["resource_usage"]["fill_buffers"] = {"capacity": self.cache.FILL_BUFFER_COUNT,
                                                              "snapshots": self.fill_buffer_snapshots}
            timelineJson["resource_usage"]["write_buffers"] = {"capacity": self.cache.WRITE_BUFFER_COUNT,
                                                               "snapshots": self.write_buffer_snapshots}
        return json.dumps(timelineJson)

_scheduler = Scheduler()
